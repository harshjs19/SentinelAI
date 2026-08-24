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
        if not self.predictions:
            if self.status is not AnalysisStatus.INSUFFICIENT_EVIDENCE:
                raise ValueError(
                    "Analysis without predictions must have insufficient-evidence status"
                )
            if self.condition is not ConditionState.INDETERMINATE:
                raise ValueError("Analysis without predictions must have indeterminate condition")
            if self.findings:
                raise ValueError("Analysis without predictions cannot contain findings")
            if self.health_score is not None:
                raise ValueError("Analysis without predictions cannot contain a health score")
            if self.risk_level is not None:
                raise ValueError("Analysis without predictions cannot contain a risk level")
            if self.limitations:
                raise ValueError("Analysis without predictions cannot contain limitations")
        elif self.status is AnalysisStatus.INSUFFICIENT_EVIDENCE:
            raise ValueError("Analysis with predictions cannot have insufficient-evidence status")

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
