from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_serializer

from ai_core.model_capabilities import ModelLifecycleStatus
from domain.entities.finding import Finding
from domain.enums.analysis_limitation import AnalysisLimitation
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from domain.enums.modality import Modality
from domain.enums.risk_level import RiskLevel
from shared.evidence.canonical import utc_datetime_string
from shared.evidence.models import EvidencePackage
from shared.evidence.provenance import SourceKind


class PredictionEvidenceSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    modality: Modality
    label: str
    confidence: float = Field(ge=0, le=1)


class FindingEvidenceSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    modality: Modality
    code: str
    condition: ConditionState
    confidence: float = Field(ge=0, le=1)
    confidence_kind: ConfidenceKind


class MachineEvidenceSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    machine_id: UUID
    name: str
    asset_type: str


class AnalysisEvidenceSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: UUID
    machine_id: UUID
    predictions: tuple[PredictionEvidenceSchema, ...]
    findings: tuple[FindingEvidenceSchema, ...]
    condition: ConditionState
    status: AnalysisStatus
    health_score: float | None
    risk_level: RiskLevel | None
    limitations: tuple[AnalysisLimitation, ...]
    created_at: AwareDatetime
    top_findings: tuple[FindingEvidenceSchema, ...]

    @field_serializer("created_at", when_used="json")
    def serialize_created_at(self, value: datetime) -> str:
        return utc_datetime_string(value)


class SourceProvenanceSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    modality: Modality
    source_kind: SourceKind
    sha256: str
    size_bytes: int = Field(ge=0)
    content_type: str


class ModelProvenanceSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_id: str
    modality: Modality
    status: ModelLifecycleStatus
    runtime_default: bool
    validated_scope: str
    evaluation_reference: str
    confidence_semantics: str


class EvidenceClaimSupportSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    condition_available: bool
    failure_probability_available: bool
    fault_severity_available: bool
    health_score_available: bool
    operational_risk_available: bool


class EvidencePackageSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str
    package_id: str
    package_digest_sha256: str
    created_at: AwareDatetime
    machine: MachineEvidenceSchema
    analysis: AnalysisEvidenceSchema
    sources: tuple[SourceProvenanceSchema, ...]
    models: tuple[ModelProvenanceSchema, ...]
    claim_support: EvidenceClaimSupportSchema

    @field_serializer("created_at", when_used="json")
    def serialize_created_at(self, value: datetime) -> str:
        return utc_datetime_string(value)

    @classmethod
    def from_domain(cls, package: EvidencePackage) -> "EvidencePackageSchema":
        analysis = package.analysis
        return cls(
            schema_version=package.schema_version,
            package_id=package.package_id,
            package_digest_sha256=package.package_digest_sha256,
            created_at=package.created_at,
            machine=MachineEvidenceSchema(
                machine_id=package.machine.machine_id,
                name=package.machine.name,
                asset_type=package.machine.asset_type,
            ),
            analysis=AnalysisEvidenceSchema(
                analysis_id=analysis.analysis_id,
                machine_id=analysis.machine_id,
                predictions=tuple(
                    PredictionEvidenceSchema(
                        modality=prediction.modality,
                        label=prediction.label,
                        confidence=prediction.confidence,
                    )
                    for prediction in analysis.predictions
                ),
                findings=tuple(_finding_schema(finding) for finding in analysis.findings),
                condition=analysis.condition,
                status=analysis.status,
                health_score=analysis.health_score,
                risk_level=analysis.risk_level,
                limitations=analysis.limitations,
                created_at=analysis.created_at,
                top_findings=tuple(_finding_schema(finding) for finding in analysis.top_findings),
            ),
            sources=tuple(
                SourceProvenanceSchema(
                    modality=source.modality,
                    source_kind=source.source_kind,
                    sha256=source.sha256,
                    size_bytes=source.size_bytes,
                    content_type=source.content_type,
                )
                for source in package.sources
            ),
            models=tuple(
                ModelProvenanceSchema(
                    model_id=model.model_id,
                    modality=model.modality,
                    status=model.status,
                    runtime_default=model.runtime_default,
                    validated_scope=model.validated_scope,
                    evaluation_reference=model.evaluation_reference,
                    confidence_semantics=model.confidence_semantics,
                )
                for model in package.models
            ),
            claim_support=EvidenceClaimSupportSchema(
                condition_available=package.claim_support.condition_available,
                failure_probability_available=package.claim_support.failure_probability_available,
                fault_severity_available=package.claim_support.fault_severity_available,
                health_score_available=package.claim_support.health_score_available,
                operational_risk_available=package.claim_support.operational_risk_available,
            ),
        )


def _finding_schema(finding: Finding) -> FindingEvidenceSchema:
    return FindingEvidenceSchema(
        modality=finding.modality,
        code=finding.code,
        condition=finding.condition,
        confidence=finding.confidence,
        confidence_kind=finding.confidence_kind,
    )
