from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from domain.entities.prediction import Prediction
from domain.enums.risk_level import RiskLevel
from domain.value_objects.health_score import HealthScore


@dataclass(frozen=True)
class Analysis:
    id: UUID
    machine_id: UUID
    predictions: tuple[Prediction, ...]
    health_score: HealthScore
    risk_level: RiskLevel
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.predictions:
            raise ValueError("Analysis must contain at least one prediction")
