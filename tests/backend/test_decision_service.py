from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest

from backend.app.services.decision_service import DecisionService
from domain.entities.analysis import Analysis
from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from inference.event_bus import EventBus
from inference.events import AnalysisProduced
from modules.decision.engine import DecisionEngine


class RecordingDecisionEngine(DecisionEngine):
    def __init__(self, analysis: Analysis) -> None:
        self.analysis = analysis
        self.calls: list[tuple[UUID, tuple[Prediction, ...]]] = []

    def evaluate(self, machine_id: UUID, predictions: Sequence[Prediction]) -> Analysis:
        self.calls.append((machine_id, tuple(predictions)))
        return self.analysis


@pytest.mark.asyncio
async def test_returns_analysis_and_publishes_exactly_one_event() -> None:
    machine_id = uuid4()
    prediction = Prediction(Modality.TIMESERIES, "bearing_fault", 0.91)
    analysis = DecisionEngine().evaluate(machine_id, [prediction])
    engine = RecordingDecisionEngine(analysis)
    event_bus = EventBus()
    events: list[AnalysisProduced] = []

    async def record(event: AnalysisProduced) -> None:
        events.append(event)

    event_bus.subscribe(AnalysisProduced, record)

    result = await DecisionService(engine, event_bus).analyze(machine_id, [prediction])

    assert result is analysis
    assert engine.calls == [(machine_id, (prediction,))]
    assert events == [AnalysisProduced(machine_id=machine_id, analysis=analysis)]
    assert events[0].analysis is result


@pytest.mark.asyncio
async def test_event_publication_failure_propagates() -> None:
    machine_id = uuid4()
    prediction = Prediction(Modality.TIMESERIES, "healthy", 0.85)
    analysis = DecisionEngine().evaluate(machine_id, [prediction])
    event_bus = EventBus()

    async def fail(event: AnalysisProduced) -> None:
        raise RuntimeError("consumer failed")

    event_bus.subscribe(AnalysisProduced, fail)

    with pytest.raises(RuntimeError, match="consumer failed"):
        await DecisionService(RecordingDecisionEngine(analysis), event_bus).analyze(
            machine_id,
            [prediction],
        )
