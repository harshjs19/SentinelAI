from collections.abc import Sequence
from uuid import UUID

from domain.entities.analysis import Analysis
from domain.entities.prediction import Prediction
from inference.event_bus import EventBus
from inference.events import AnalysisProduced
from modules.decision.engine import DecisionEngine


class DecisionService:
    def __init__(self, engine: DecisionEngine, event_bus: EventBus) -> None:
        self._engine = engine
        self._event_bus = event_bus

    async def analyze(
        self,
        machine_id: UUID,
        predictions: Sequence[Prediction],
    ) -> Analysis:
        analysis = self._engine.evaluate(machine_id, predictions)
        await self._event_bus.publish(AnalysisProduced(machine_id=machine_id, analysis=analysis))
        return analysis
