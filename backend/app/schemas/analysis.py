from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from domain.enums.analysis_limitation import AnalysisLimitation
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from domain.enums.modality import Modality
from domain.enums.risk_level import RiskLevel


class FindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    modality: Modality
    code: str
    condition: ConditionState
    confidence: float = Field(ge=0, le=1)
    confidence_kind: ConfidenceKind


class AnalysisResponse(BaseModel):
    machine_id: UUID
    status: AnalysisStatus
    condition: ConditionState
    findings: list[FindingResponse]
    top_findings: list[FindingResponse]
    health_score: float | None
    risk_level: RiskLevel | None
    limitations: list[AnalysisLimitation]
