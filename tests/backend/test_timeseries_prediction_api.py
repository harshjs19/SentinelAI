from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from uuid import UUID, uuid4

import httpx
import pytest

import backend.app.dependencies as dependencies
from ai_core.model_capabilities import get_runtime_default_capability
from ai_core.model_provenance import snapshot_producing_model_context
from backend.app.dependencies import (
    get_machine_service,
    get_timeseries_inference_service,
)
from backend.app.main import app
from backend.app.services.timeseries_inference_service import TimeseriesInferenceService
from domain.entities.machine import Machine
from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from inference.event_bus import EventBus
from inference.events import PredictionProduced
from inference.orchestrator import InferenceOrchestrator
from modules.timeseries.config import RAW_FEATURES


class FakeMachineService:
    def __init__(self, machine: Machine) -> None:
        self.machine = machine

    async def get_machine(self, machine_id: UUID) -> Machine | None:
        return self.machine if machine_id == self.machine.id else None


class FakeTimeseriesPredictor:
    def __init__(self) -> None:
        self.inputs: list[Mapping[str, float]] = []

    def predict(self, input_data: Mapping[str, float]) -> Prediction:
        self.inputs.append(input_data)
        return Prediction(Modality.TIMESERIES, "bearing_fault", 0.93)


@dataclass(frozen=True)
class ApiContext:
    machine: Machine
    predictor: FakeTimeseriesPredictor
    events: list[PredictionProduced]


@pytest.fixture
def api_context() -> Iterator[ApiContext]:
    machine = Machine(uuid4(), "Pump-101", "pump")
    machine_service = FakeMachineService(machine)
    predictor = FakeTimeseriesPredictor()
    event_bus = EventBus()
    orchestrator = InferenceOrchestrator(event_bus)
    orchestrator.register(
        Modality.TIMESERIES,
        predictor,
        input_type=Mapping,
        producing_model=snapshot_producing_model_context(
            get_runtime_default_capability(Modality.TIMESERIES)
        ),
    )
    inference_service = TimeseriesInferenceService(orchestrator)
    events: list[PredictionProduced] = []

    async def record(event: PredictionProduced) -> None:
        events.append(event)

    event_bus.subscribe(PredictionProduced, record)
    app.dependency_overrides[get_machine_service] = lambda: machine_service
    app.dependency_overrides[get_timeseries_inference_service] = lambda: inference_service
    yield ApiContext(machine=machine, predictor=predictor, events=events)
    app.dependency_overrides.pop(get_machine_service, None)
    app.dependency_overrides.pop(get_timeseries_inference_service, None)


def request_body() -> dict[str, object]:
    return {
        "samples": [
            {feature: 1.0 for feature in RAW_FEATURES},
            {feature: 3.0 for feature in RAW_FEATURES},
        ]
    }


@pytest.mark.asyncio
async def test_known_machine_returns_prediction_and_emits_event(api_context: ApiContext) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{api_context.machine.id}/predictions/timeseries",
            json=request_body(),
        )

    assert response.status_code == 200
    assert response.json() == {
        "machine_id": str(api_context.machine.id),
        "modality": "timeseries",
        "label": "bearing_fault",
        "confidence": 0.93,
    }
    assert len(api_context.predictor.inputs) == 1
    assert api_context.events == [
        PredictionProduced(
            machine_id=api_context.machine.id,
            prediction=Prediction(Modality.TIMESERIES, "bearing_fault", 0.93),
        )
    ]


@pytest.mark.asyncio
async def test_unknown_machine_returns_not_found(api_context: ApiContext) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{uuid4()}/predictions/timeseries",
            json=request_body(),
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Machine not found"}
    assert api_context.predictor.inputs == []
    assert api_context.events == []


@pytest.mark.asyncio
async def test_empty_measurement_window_is_rejected(api_context: ApiContext) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{api_context.machine.id}/predictions/timeseries",
            json={"samples": []},
        )

    assert response.status_code == 422
    assert api_context.predictor.inputs == []
    assert api_context.events == []


@pytest.mark.asyncio
async def test_missing_model_returns_service_unavailable(
    api_context: ApiContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_model_orchestrator() -> InferenceOrchestrator:
        raise FileNotFoundError("C:/private/models/missing.joblib")

    app.dependency_overrides.pop(get_timeseries_inference_service, None)
    dependencies.get_timeseries_inference_service.cache_clear()
    monkeypatch.setattr(
        dependencies,
        "get_inference_orchestrator",
        missing_model_orchestrator,
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{api_context.machine.id}/predictions/timeseries",
            json=request_body(),
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Time-series model is not available"}
    assert api_context.predictor.inputs == []
    assert api_context.events == []
