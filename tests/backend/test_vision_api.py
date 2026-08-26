import io
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import httpx
import numpy as np
import pytest
from PIL import Image

import backend.app.dependencies as dependencies
from ai_core.model_capabilities import get_runtime_default_capability
from ai_core.model_provenance import snapshot_producing_model_context
from backend.app.dependencies import (
    get_decision_service,
    get_machine_service,
    get_vision_inference_service,
)
from backend.app.main import app
from backend.app.services.decision_service import DecisionService
from backend.app.services.vision_inference_service import VisionInferenceService
from domain.entities.machine import Machine
from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from inference.event_bus import EventBus
from inference.events import AnalysisProduced, PredictionProduced
from inference.orchestrator import InferenceOrchestrator
from modules.decision.engine import DecisionEngine
from modules.vision.input import VisionInput


class FakeMachineService:
    def __init__(self, machine: Machine) -> None:
        self.machine = machine

    async def get_machine(self, machine_id: UUID) -> Machine | None:
        return self.machine if machine_id == self.machine.id else None


class FakeVisionPredictor:
    def __init__(self) -> None:
        self.inputs: list[VisionInput] = []

    def predict(self, input_data: VisionInput) -> Prediction:
        self.inputs.append(input_data)
        return Prediction(Modality.VISION, "visual_anomaly", 0.91)


@dataclass(frozen=True)
class ApiContext:
    machine: Machine
    predictor: FakeVisionPredictor
    events: list[object]


@pytest.fixture
def api_context() -> Iterator[ApiContext]:
    machine = Machine(uuid4(), "PCB-101", "pcb1")
    predictor = FakeVisionPredictor()
    event_bus = EventBus()
    orchestrator = InferenceOrchestrator(event_bus)
    orchestrator.register(
        Modality.VISION,
        predictor,
        input_type=VisionInput,
        producing_model=snapshot_producing_model_context(
            get_runtime_default_capability(Modality.VISION)
        ),
    )
    inference_service = VisionInferenceService(orchestrator, ("pcb1",))
    events: list[object] = []

    async def record_prediction(event: PredictionProduced) -> None:
        events.append(event)

    async def record_analysis(event: AnalysisProduced) -> None:
        events.append(event)

    event_bus.subscribe(PredictionProduced, record_prediction)
    event_bus.subscribe(AnalysisProduced, record_analysis)
    app.dependency_overrides[get_machine_service] = lambda: FakeMachineService(machine)
    app.dependency_overrides[get_vision_inference_service] = lambda: inference_service
    app.dependency_overrides[get_decision_service] = lambda: DecisionService(
        DecisionEngine(), event_bus
    )
    yield ApiContext(machine, predictor, events)
    app.dependency_overrides.pop(get_machine_service, None)
    app.dependency_overrides.pop(get_vision_inference_service, None)
    app.dependency_overrides.pop(get_decision_service, None)


def image_upload(format_name: str = "PNG") -> dict[str, tuple[str, bytes, str]]:
    buffer = io.BytesIO()
    pixels = np.zeros((6, 8, 3), dtype=np.uint8)
    Image.fromarray(pixels, mode="RGB").save(buffer, format_name)
    content_type = "image/png" if format_name == "PNG" else "image/jpeg"
    return {"file": ("inspection.bin", buffer.getvalue(), content_type)}


@pytest.mark.asyncio
async def test_known_pcb1_machine_returns_vision_prediction(api_context: ApiContext) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{api_context.machine.id}/predictions/vision",
            files=image_upload("JPEG"),
        )

    assert response.status_code == 200
    assert response.json() == {
        "machine_id": str(api_context.machine.id),
        "modality": "vision",
        "label": "visual_anomaly",
        "confidence": 0.91,
    }
    assert len(api_context.predictor.inputs) == 1
    assert [type(event) for event in api_context.events] == [PredictionProduced]


@pytest.mark.asyncio
async def test_unknown_machine_returns_not_found(api_context: ApiContext) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{uuid4()}/predictions/vision",
            files=image_upload(),
        )

    assert response.status_code == 404
    assert api_context.predictor.inputs == []
    assert api_context.events == []


@pytest.mark.asyncio
async def test_unsupported_asset_type_returns_client_error(api_context: ApiContext) -> None:
    machine = Machine(api_context.machine.id, "Bearing-101", "bearing")
    app.dependency_overrides[get_machine_service] = lambda: FakeMachineService(machine)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{machine.id}/predictions/vision",
            files=image_upload(),
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Vision model supports these asset types: pcb1"}
    assert api_context.events == []


@pytest.mark.asyncio
async def test_malformed_image_returns_client_error(api_context: ApiContext) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{api_context.machine.id}/predictions/vision",
            files={"file": ("bad.png", b"not-an-image", "image/png")},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Vision input is not a valid JPEG or PNG image"}
    assert api_context.events == []


@pytest.mark.asyncio
async def test_missing_model_returns_safe_service_unavailable(
    api_context: ApiContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_predictor() -> None:
        raise FileNotFoundError("C:/private/models/missing-vision.joblib")

    app.dependency_overrides.pop(get_vision_inference_service, None)
    dependencies.get_vision_inference_service.cache_clear()
    monkeypatch.setattr(dependencies, "get_vision_predictor", missing_predictor)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{api_context.machine.id}/predictions/vision",
            files=image_upload(),
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Vision model is not available"}
    assert "private" not in response.text
    assert api_context.events == []


@pytest.mark.asyncio
async def test_vision_analysis_is_provisional_and_emits_events_in_order(
    api_context: ApiContext,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{api_context.machine.id}/analyses/vision",
            files=image_upload(),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "provisional"
    assert body["condition"] == "abnormal"
    assert body["health_score"] is None
    assert body["risk_level"] is None
    assert body["findings"] == [
        {
            "modality": "vision",
            "code": "visual_anomaly",
            "condition": "abnormal",
            "confidence": 0.91,
            "confidence_kind": "raw",
        }
    ]
    assert [type(event) for event in api_context.events] == [
        PredictionProduced,
        AnalysisProduced,
    ]
