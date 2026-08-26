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
    get_thermal_inference_service,
)
from backend.app.main import app
from backend.app.services.decision_service import DecisionService
from backend.app.services.thermal_inference_service import ThermalInferenceService
from domain.entities.machine import Machine
from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from inference.event_bus import EventBus
from inference.events import AnalysisProduced, PredictionProduced
from inference.orchestrator import InferenceOrchestrator
from modules.decision.engine import DecisionEngine
from modules.thermal.input import ThermalInput


class FakeMachineService:
    def __init__(self, machine: Machine) -> None:
        self.machine = machine

    async def get_machine(self, machine_id: UUID) -> Machine | None:
        return self.machine if machine_id == self.machine.id else None


class FakeThermalPredictor:
    def __init__(self) -> None:
        self.inputs: list[ThermalInput] = []
        self.label = "gear_wear_75"

    def predict(self, input_data: ThermalInput) -> Prediction:
        self.inputs.append(input_data)
        return Prediction(Modality.THERMAL, self.label, 0.99)


@dataclass(frozen=True)
class ApiContext:
    machine: Machine
    predictor: FakeThermalPredictor
    events: list[object]


@pytest.fixture
def api_context() -> Iterator[ApiContext]:
    machine = Machine(uuid4(), "CORA-Rig-101", "rotating_electromechanical_system")
    predictor = FakeThermalPredictor()
    event_bus = EventBus()
    orchestrator = InferenceOrchestrator(event_bus)
    orchestrator.register(
        Modality.THERMAL,
        predictor,
        input_type=ThermalInput,
        producing_model=snapshot_producing_model_context(
            get_runtime_default_capability(Modality.THERMAL)
        ),
    )
    inference_service = ThermalInferenceService(
        orchestrator,
        ("rotating_electromechanical_system",),
    )
    events: list[object] = []

    async def record_prediction(event: PredictionProduced) -> None:
        events.append(event)

    async def record_analysis(event: AnalysisProduced) -> None:
        events.append(event)

    event_bus.subscribe(PredictionProduced, record_prediction)
    event_bus.subscribe(AnalysisProduced, record_analysis)
    app.dependency_overrides[get_machine_service] = lambda: FakeMachineService(machine)
    app.dependency_overrides[get_thermal_inference_service] = lambda: inference_service
    app.dependency_overrides[get_decision_service] = lambda: DecisionService(
        DecisionEngine(), event_bus
    )
    yield ApiContext(machine, predictor, events)
    app.dependency_overrides.pop(get_machine_service, None)
    app.dependency_overrides.pop(get_thermal_inference_service, None)
    app.dependency_overrides.pop(get_decision_service, None)
    dependencies.get_thermal_inference_service.cache_clear()


def image_upload(format_name: str = "PNG") -> dict[str, tuple[str, bytes, str]]:
    buffer = io.BytesIO()
    pixels = np.full((6, 8, 3), 100, dtype=np.uint8)
    Image.fromarray(pixels, mode="RGB").save(buffer, format_name)
    content_type = "image/png" if format_name == "PNG" else "image/jpeg"
    return {"file": ("thermogram.bin", buffer.getvalue(), content_type)}


@pytest.mark.asyncio
async def test_known_compatible_machine_returns_thermal_prediction(
    api_context: ApiContext,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{api_context.machine.id}/predictions/thermal",
            files=image_upload("JPEG"),
        )

    assert response.status_code == 200
    assert response.json() == {
        "machine_id": str(api_context.machine.id),
        "modality": "thermal",
        "label": "gear_wear_75",
        "confidence": 0.99,
    }
    assert len(api_context.predictor.inputs) == 1
    assert [type(event) for event in api_context.events] == [PredictionProduced]


@pytest.mark.asyncio
async def test_unknown_machine_returns_not_found(api_context: ApiContext) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{uuid4()}/predictions/thermal",
            files=image_upload(),
        )

    assert response.status_code == 404
    assert api_context.predictor.inputs == []
    assert api_context.events == []


@pytest.mark.asyncio
async def test_unsupported_asset_type_returns_client_error(api_context: ApiContext) -> None:
    machine = Machine(api_context.machine.id, "PCB-101", "pcb1")
    app.dependency_overrides[get_machine_service] = lambda: FakeMachineService(machine)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{machine.id}/predictions/thermal",
            files=image_upload(),
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": ("Thermal model supports these asset types: rotating_electromechanical_system")
    }
    assert api_context.predictor.inputs == []
    assert api_context.events == []


@pytest.mark.asyncio
async def test_malformed_image_returns_client_error(api_context: ApiContext) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{api_context.machine.id}/predictions/thermal",
            files={"file": ("bad.png", b"not-an-image", "image/png")},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Thermal input is not a valid JPEG or PNG image"}
    assert api_context.predictor.inputs == []
    assert api_context.events == []


@pytest.mark.asyncio
async def test_missing_model_returns_safe_service_unavailable(
    api_context: ApiContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_predictor() -> None:
        raise FileNotFoundError("C:/private/models/missing-thermal.joblib")

    app.dependency_overrides.pop(get_thermal_inference_service, None)
    dependencies.get_thermal_inference_service.cache_clear()
    monkeypatch.setattr(dependencies, "get_thermal_predictor", missing_predictor)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{api_context.machine.id}/predictions/thermal",
            files=image_upload(),
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Thermal model is not available"}
    assert "private" not in response.text
    assert api_context.predictor.inputs == []
    assert api_context.events == []


@pytest.mark.asyncio
async def test_fault_analysis_is_provisional_without_health_or_risk(
    api_context: ApiContext,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{api_context.machine.id}/analyses/thermal",
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
            "modality": "thermal",
            "code": "gear_wear_75",
            "condition": "abnormal",
            "confidence": 0.99,
            "confidence_kind": "raw",
        }
    ]
    assert [type(event) for event in api_context.events] == [
        PredictionProduced,
        AnalysisProduced,
    ]


@pytest.mark.asyncio
async def test_healthy_analysis_is_normal(api_context: ApiContext) -> None:
    api_context.predictor.label = "healthy"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{api_context.machine.id}/analyses/thermal",
            files=image_upload(),
        )

    assert response.status_code == 200
    assert response.json()["condition"] == "normal"
    assert response.json()["health_score"] is None
    assert response.json()["risk_level"] is None
