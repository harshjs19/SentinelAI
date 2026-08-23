from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from uuid import UUID, uuid4

import httpx
import pytest

import backend.app.dependencies as dependencies
from backend.app.dependencies import (
    get_decision_service,
    get_machine_service,
    get_timeseries_inference_service,
)
from backend.app.main import app
from backend.app.services.decision_service import DecisionService
from backend.app.services.timeseries_inference_service import TimeseriesInferenceService
from domain.entities.machine import Machine
from domain.entities.prediction import Prediction
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.modality import Modality
from inference.event_bus import EventBus
from inference.events import AnalysisProduced, PredictionProduced
from inference.orchestrator import InferenceOrchestrator
from modules.decision.engine import DecisionEngine
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
    events: list[object]


@pytest.fixture
def api_context() -> Iterator[ApiContext]:
    machine = Machine(uuid4(), "Pump-101", "pump")
    predictor = FakeTimeseriesPredictor()
    event_bus = EventBus()
    orchestrator = InferenceOrchestrator(event_bus)
    orchestrator.register(Modality.TIMESERIES, predictor, input_type=Mapping)
    events: list[object] = []

    async def record_prediction(event: PredictionProduced) -> None:
        events.append(event)

    async def record_analysis(event: AnalysisProduced) -> None:
        events.append(event)

    event_bus.subscribe(PredictionProduced, record_prediction)
    event_bus.subscribe(AnalysisProduced, record_analysis)
    app.dependency_overrides[get_machine_service] = lambda: FakeMachineService(machine)
    app.dependency_overrides[get_timeseries_inference_service] = lambda: TimeseriesInferenceService(
        orchestrator
    )
    app.dependency_overrides[get_decision_service] = lambda: DecisionService(
        DecisionEngine(), event_bus
    )
    yield ApiContext(machine=machine, predictor=predictor, events=events)
    app.dependency_overrides.pop(get_machine_service, None)
    app.dependency_overrides.pop(get_timeseries_inference_service, None)
    app.dependency_overrides.pop(get_decision_service, None)


def request_body() -> dict[str, object]:
    return {
        "samples": [
            {feature: 1.0 for feature in RAW_FEATURES},
            {feature: 3.0 for feature in RAW_FEATURES},
        ]
    }


@pytest.mark.asyncio
async def test_known_machine_returns_provisional_analysis_and_emits_events(
    api_context: ApiContext,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{api_context.machine.id}/analyses/timeseries",
            json=request_body(),
        )

    assert response.status_code == 200
    assert response.json() == {
        "machine_id": str(api_context.machine.id),
        "status": "provisional",
        "condition": "abnormal",
        "findings": [
            {
                "modality": "timeseries",
                "code": "bearing_fault",
                "condition": "abnormal",
                "confidence": 0.93,
                "confidence_kind": "raw",
            }
        ],
        "top_findings": [
            {
                "modality": "timeseries",
                "code": "bearing_fault",
                "condition": "abnormal",
                "confidence": 0.93,
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
    assert len(api_context.predictor.inputs) == 1
    assert [type(event) for event in api_context.events] == [
        PredictionProduced,
        AnalysisProduced,
    ]
    prediction_event = api_context.events[0]
    analysis_event = api_context.events[1]
    assert isinstance(prediction_event, PredictionProduced)
    assert prediction_event.prediction.label == "bearing_fault"
    assert isinstance(analysis_event, AnalysisProduced)
    assert analysis_event.analysis.status is AnalysisStatus.PROVISIONAL


@pytest.mark.asyncio
async def test_unknown_machine_returns_not_found(api_context: ApiContext) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/machines/{uuid4()}/analyses/timeseries",
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
            f"/machines/{api_context.machine.id}/analyses/timeseries",
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
            f"/machines/{api_context.machine.id}/analyses/timeseries",
            json=request_body(),
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Time-series model is not available"}
    assert api_context.predictor.inputs == []
    assert api_context.events == []
