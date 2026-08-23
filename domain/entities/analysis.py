from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from domain.entities.finding import Finding
from domain.entities.prediction import Prediction
from domain.enums.analysis_limitation import AnalysisLimitation
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from domain.enums.risk_level import RiskLevel
from domain.value_objects.health_score import HealthScore

_CONDITION_RANK = {
    ConditionState.ABNORMAL: 0,
    ConditionState.NORMAL: 1,
    ConditionState.INDETERMINATE: 2,
}


@dataclass(frozen=True)
class Analysis:
    id: UUID
    machine_id: UUID
    predictions: tuple[Prediction, ...]
    findings: tuple[Finding, ...]
    condition: ConditionState
    status: AnalysisStatus
    health_score: HealthScore | None
    risk_level: RiskLevel | None
    limitations: tuple[AnalysisLimitation, ...]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() != timedelta(0):
            raise ValueError("Analysis created_at must be timezone-aware UTC")

    @property
    def top_findings(self) -> tuple[Finding, ...]:
        return tuple(
            sorted(
                self.findings,
                key=lambda finding: (
                    _CONDITION_RANK[finding.condition],
                    -finding.confidence,
                    finding.modality.value,
                    finding.code,
                ),
            )[:3]
        )
