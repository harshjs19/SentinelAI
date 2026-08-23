import io
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import httpx
import numpy as np
import pytest
import soundfile as sf

import backend.app.dependencies as dependencies
from backend.app.dependencies import (
    get_audio_inference_service,
    get_decision_service,
    get_machine_service,
)
from backend.app.main import app
from backend.app.services.audio_inference_service import AudioInferenceService
from backend.app.services.decision_service import DecisionService
from domain.entities.machine import Machine
from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from inference.event_bus import EventBus
from inference.events import AnalysisProduced, PredictionProduced
from inference.orchestrator import InferenceOrchestrator
from modules.audio.input import AudioInput
from modules.decision.engine import DecisionEngine


class FakeMachineService:
    def __init__(self, machine: Machine) -> None:
        self.machine = machine

    async def get_machine(self, machine_id: UUID) -> Machine | None:
        return self.machine if machine_id == self.machine.id else None


class FakeAudioPredictor:
    def __init__(self) -> None:
        self.inputs: list[AudioInput] = []

    def predict(self, input_data: AudioInput) -> Prediction:
        self.inputs.append(input_data)
        return Prediction(Modality.AUDIO, "acoustic_anomaly", 0.87)


@dataclass(frozen=True)
class ApiContext:
    machine: Machine
    predictor: FakeAudioPredictor
    events: list[object]


@pytest.fixture
def api_context() -> Iterator[ApiContext]:
    machine = Machine(uuid4(), "Bearing-101", "bearing")
    predictor = FakeAudioPredictor()
    event_bus = EventBus()
    orchestrator = InferenceOrchestrator(event_bus)
    orchestrator.register(Modality.AUDIO, predictor, input_type=AudioInput)
    inference_service = AudioInferenceService(orchestrator, ("bearing",))
    events: list[object] = []

    async def record_prediction(event: PredictionProduced) -> None:
        events.append(event)

    async def record_analysis(event: AnalysisProduced) -> None:
        events.append(event)

    event_bus.subscribe(PredictionProduced, record_prediction)
    event_bus.subscribe(AnalysisProduced, record_analysis)
    app.dependency_overrides[get_machine_service] = lambda: FakeMachineService(machine)
    app.dependency_overrides[get_audio_inference_service] = lambda: inference_service
    app.dependency_overrides[get_decision_service] = lambda: DecisionService(
        DecisionEngine(), event_bus
    )
    yield ApiContext(machine=machine, predictor=predictor, events=events)
    app.dependency_overrides.pop(get_machine_service, None)
    app.dependency_overrides.pop(get_audio_inference_service, None)
    app.dependency_overrides.pop(get_decision_service, None)


def wav_upload() -> dict[str, tuple[str, bytes, str]]:
    buffer = io.BytesIO()
    sf.write(buffer, np.zeros(1_600), 16_000, format="WAV", subtype="PCM_16")
    return {"file": ("sample.wav", buffer.getvalue(), "audio/wav")}


@pytest.mark.asyncio
async def test_known_supported_machine_returns_audio_prediction(api_context: ApiContext) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{api_context.machine.id}/predictions/audio",
            files=wav_upload(),
        )

    assert response.status_code == 200
    assert response.json() == {
        "machine_id": str(api_context.machine.id),
        "modality": "audio",
        "label": "acoustic_anomaly",
        "confidence": 0.87,
    }
    assert len(api_context.predictor.inputs) == 1
    assert [type(event) for event in api_context.events] == [PredictionProduced]


@pytest.mark.asyncio
async def test_unknown_machine_returns_not_found(api_context: ApiContext) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{uuid4()}/predictions/audio",
            files=wav_upload(),
        )

    assert response.status_code == 404
    assert api_context.predictor.inputs == []
    assert api_context.events == []


@pytest.mark.asyncio
async def test_unsupported_asset_type_returns_client_error(api_context: ApiContext) -> None:
    unsupported = Machine(api_context.machine.id, "Pump-101", "pump")
    app.dependency_overrides[get_machine_service] = lambda: FakeMachineService(unsupported)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{unsupported.id}/predictions/audio",
            files=wav_upload(),
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Audio model supports these asset types: bearing"}
    assert api_context.events == []


@pytest.mark.asyncio
async def test_malformed_audio_returns_client_error(api_context: ApiContext) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{api_context.machine.id}/predictions/audio",
            files={"file": ("bad.wav", b"not-a-wav", "audio/wav")},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Audio input is not a valid WAV file"}
    assert api_context.events == []


@pytest.mark.asyncio
async def test_missing_audio_model_returns_service_unavailable(
    api_context: ApiContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_audio_predictor() -> None:
        raise FileNotFoundError("C:/private/models/missing-audio.joblib")

    app.dependency_overrides.pop(get_audio_inference_service, None)
    dependencies.get_audio_inference_service.cache_clear()
    monkeypatch.setattr(dependencies, "get_audio_predictor", missing_audio_predictor)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{api_context.machine.id}/predictions/audio",
            files=wav_upload(),
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Audio model is not available"}
    assert api_context.predictor.inputs == []
    assert api_context.events == []


@pytest.mark.asyncio
async def test_audio_analysis_is_provisional_and_emits_events_in_order(
    api_context: ApiContext,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{api_context.machine.id}/analyses/audio",
            files=wav_upload(),
        )

    assert response.status_code == 200
    assert response.json() == {
        "machine_id": str(api_context.machine.id),
        "status": "provisional",
        "condition": "abnormal",
        "findings": [
            {
                "modality": "audio",
                "code": "acoustic_anomaly",
                "condition": "abnormal",
                "confidence": 0.87,
                "confidence_kind": "raw",
            }
        ],
        "top_findings": [
            {
                "modality": "audio",
                "code": "acoustic_anomaly",
                "condition": "abnormal",
                "confidence": 0.87,
                "confidence_kind": "raw",
            }
        ],
        "health_score": None,
        "risk_level": None,
        "limitations": [
            "uncalibrated_confidence",
            "fault_severity_unavailable",
            "risk_context_unavailable",
            "single_modality_evidence",
        ],
    }
    assert [type(event) for event in api_context.events] == [
        PredictionProduced,
        AnalysisProduced,
    ]
