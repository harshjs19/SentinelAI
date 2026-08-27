from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ai_core.model_capabilities import ModelLifecycleStatus
from backend.app.schemas.timeseries import TimeseriesSample
from domain.entities.analysis import Analysis
from domain.enums.analysis_limitation import AnalysisLimitation
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from domain.enums.modality import Modality
from domain.enums.risk_level import RiskLevel
from modules.copilot.contracts import (
    CopilotIntent,
    FallbackReason,
    GenerationStatus,
    RequestDisposition,
)
from modules.copilot.report import MaintenanceReport
from modules.retriever.models import RetrievalBundle, RetrievalLane
from shared.evidence.models import EvidencePackage
from shared.evidence.provenance import SourceKind


class TimeseriesMaintenanceReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    samples: list[TimeseriesSample] = Field(min_length=2)
    intent: CopilotIntent
    question: str | None = Field(default=None, max_length=500)


class MaintenanceFindingResponse(BaseModel):
    finding_id: str
    modality: Modality
    code: str
    condition: ConditionState
    confidence: float = Field(ge=0, le=1)
    confidence_kind: ConfidenceKind


class MaintenanceNarrativeItemResponse(BaseModel):
    finding_id: str
    text: str
    citation_ids: tuple[str, ...]


class MaintenanceNarrativeResponse(BaseModel):
    executive_summary: str
    finding_explanations: tuple[MaintenanceNarrativeItemResponse, ...]
    inspection_considerations: tuple[MaintenanceNarrativeItemResponse, ...]
    knowledge_gap_statement: str | None


class MaintenanceLimitationsResponse(BaseModel):
    analysis_limitations: tuple[AnalysisLimitation, ...]
    model_scope_limitations: tuple[str, ...]
    unavailable_claims: tuple[str, ...]
    generation_limitations: tuple[str, ...]


class MaintenanceClaimSupportResponse(BaseModel):
    condition_available: bool
    failure_probability_available: bool
    fault_severity_available: bool
    health_score_available: bool
    operational_risk_available: bool


class MaintenanceAnalysisResponse(BaseModel):
    condition: ConditionState
    status: AnalysisStatus
    findings: tuple[MaintenanceFindingResponse, ...]
    health_score: float | None
    risk_level: RiskLevel | None
    claim_support: MaintenanceClaimSupportResponse


class MaintenanceModelProvenanceResponse(BaseModel):
    model_id: str
    modality: Modality
    status: ModelLifecycleStatus
    runtime_default_at_execution: bool
    validated_scope: str
    confidence_semantics: str


class MaintenanceCitationResponse(BaseModel):
    citation_id: str
    title: str
    publisher: str
    section: str
    fault_code: str
    asset_type: str
    matched_intent: str
    source_lane: RetrievalLane


class MaintenanceSafetyResponse(BaseModel):
    valid: bool
    violation_codes: tuple[str, ...]
    validator_policy_version: str
    repair_attempted: bool


class MaintenanceReportResponse(BaseModel):
    report_id: UUID
    machine_id: UUID
    generated_at: AwareDatetime
    generation_status: GenerationStatus
    fallback_reason: FallbackReason | None
    request_disposition: RequestDisposition
    request_intent: CopilotIntent
    analysis: MaintenanceAnalysisResponse
    narrative: MaintenanceNarrativeResponse
    limitations: MaintenanceLimitationsResponse
    citations: tuple[MaintenanceCitationResponse, ...]
    producing_models: tuple[MaintenanceModelProvenanceResponse, ...]
    safety_validation: MaintenanceSafetyResponse
    disclaimer: str

    @classmethod
    def from_domain(cls, report: MaintenanceReport) -> "MaintenanceReportResponse":
        return cls(
            report_id=report.report_id,
            machine_id=report.machine.machine_id,
            generated_at=report.generated_at,
            generation_status=report.generation_status,
            fallback_reason=report.fallback_reason,
            request_disposition=report.request_disposition,
            request_intent=report.request_intent,
            analysis=MaintenanceAnalysisResponse(
                condition=report.analysis.condition,
                status=report.analysis.status,
                findings=tuple(
                    MaintenanceFindingResponse.model_validate(
                        finding,
                        from_attributes=True,
                    )
                    for finding in report.analysis.findings
                ),
                health_score=report.analysis.health_score,
                risk_level=report.analysis.risk_level,
                claim_support=MaintenanceClaimSupportResponse.model_validate(
                    report.analysis.claim_support,
                    from_attributes=True,
                ),
            ),
            narrative=MaintenanceNarrativeResponse(
                executive_summary=report.narrative.executive_summary,
                finding_explanations=tuple(
                    MaintenanceNarrativeItemResponse.model_validate(
                        item,
                        from_attributes=True,
                    )
                    for item in report.narrative.finding_explanations
                ),
                inspection_considerations=tuple(
                    MaintenanceNarrativeItemResponse.model_validate(
                        item,
                        from_attributes=True,
                    )
                    for item in report.narrative.inspection_considerations
                ),
                knowledge_gap_statement=report.narrative.knowledge_gap_statement,
            ),
            limitations=MaintenanceLimitationsResponse.model_validate(
                report.limitations,
                from_attributes=True,
            ),
            citations=tuple(
                MaintenanceCitationResponse(
                    citation_id=citation.citation_id,
                    title=citation.title,
                    publisher=citation.publisher,
                    section=citation.section,
                    fault_code=citation.fault_code,
                    asset_type=citation.asset_type,
                    matched_intent=citation.matched_intent,
                    source_lane=citation.source_lane,
                )
                for citation in report.citations
            ),
            producing_models=tuple(
                MaintenanceModelProvenanceResponse(
                    model_id=model.model_id,
                    modality=model.modality,
                    status=model.status,
                    runtime_default_at_execution=model.runtime_default,
                    validated_scope=model.validated_scope,
                    confidence_semantics=model.confidence_semantics,
                )
                for model in report.producing_models
            ),
            safety_validation=MaintenanceSafetyResponse(
                valid=report.safety_validation.valid,
                violation_codes=tuple(
                    violation.code.value for violation in report.safety_validation.violations
                ),
                validator_policy_version=(report.safety_validation.validator_policy_version),
                repair_attempted=report.safety_validation.repair_attempted,
            ),
            disclaimer=report.disclaimer,
        )


class MaintenanceReportSummaryResponse(BaseModel):
    report_id: UUID
    machine_id: UUID
    generated_at: AwareDatetime
    generation_status: GenerationStatus
    condition: ConditionState
    analysis_status: AnalysisStatus
    executive_summary: str

    @classmethod
    def from_domain(
        cls,
        report: MaintenanceReport,
    ) -> "MaintenanceReportSummaryResponse":
        return cls(
            report_id=report.report_id,
            machine_id=report.machine.machine_id,
            generated_at=report.generated_at,
            generation_status=report.generation_status,
            condition=report.analysis.condition,
            analysis_status=report.analysis.status,
            executive_summary=report.narrative.executive_summary,
        )


class MaintenanceSourceProvenanceResponse(BaseModel):
    modality: Modality
    source_kind: SourceKind
    sha256: str
    size_bytes: int = Field(ge=0)
    content_type: str


class MaintenanceAnalysisBindingResponse(BaseModel):
    analysis_id: UUID
    machine_id: UUID
    condition: ConditionState
    status: AnalysisStatus
    created_at: AwareDatetime


class MaintenanceEvidencePackageIdentityResponse(BaseModel):
    package_id: str
    package_digest_sha256: str
    schema_version: str
    created_at: AwareDatetime
    analysis_id: UUID


class MaintenanceRetrievalBundleIdentityResponse(BaseModel):
    retrieval_bundle_digest_sha256: str
    evidence_package_id: str
    evidence_package_digest_sha256: str
    corpus_digest_sha256: str
    embedding_model_id: str
    embedding_model_revision: str
    schema_version: str


class MaintenanceReportBindingResponse(BaseModel):
    report_id: UUID
    report_digest_sha256: str
    schema_version: str
    generation_status: GenerationStatus
    generated_at: AwareDatetime
    evidence_package_id: str
    evidence_package_digest_sha256: str
    retrieval_bundle_digest_sha256: str


class MaintenanceReportEvidenceResponse(BaseModel):
    report: MaintenanceReportBindingResponse
    analysis: MaintenanceAnalysisBindingResponse
    evidence_package: MaintenanceEvidencePackageIdentityResponse
    retrieval_bundle: MaintenanceRetrievalBundleIdentityResponse
    sources: tuple[MaintenanceSourceProvenanceResponse, ...]

    @classmethod
    def from_domain(
        cls,
        *,
        analysis: Analysis,
        evidence_package: EvidencePackage,
        retrieval_bundle: RetrievalBundle,
        report: MaintenanceReport,
    ) -> "MaintenanceReportEvidenceResponse":
        return cls(
            report=MaintenanceReportBindingResponse(
                report_id=report.report_id,
                report_digest_sha256=report.report_digest_sha256,
                schema_version=report.schema_version,
                generation_status=report.generation_status,
                generated_at=report.generated_at,
                evidence_package_id=report.evidence_reference.package_id,
                evidence_package_digest_sha256=(report.evidence_reference.package_digest_sha256),
                retrieval_bundle_digest_sha256=(
                    report.retrieval_reference.retrieval_bundle_digest_sha256
                ),
            ),
            analysis=MaintenanceAnalysisBindingResponse(
                analysis_id=analysis.id,
                machine_id=analysis.machine_id,
                condition=analysis.condition,
                status=analysis.status,
                created_at=analysis.created_at,
            ),
            evidence_package=MaintenanceEvidencePackageIdentityResponse(
                package_id=evidence_package.package_id,
                package_digest_sha256=evidence_package.package_digest_sha256,
                schema_version=evidence_package.schema_version,
                created_at=evidence_package.created_at,
                analysis_id=evidence_package.analysis.analysis_id,
            ),
            retrieval_bundle=MaintenanceRetrievalBundleIdentityResponse(
                retrieval_bundle_digest_sha256=(retrieval_bundle.retrieval_bundle_digest_sha256),
                evidence_package_id=retrieval_bundle.evidence_package_id,
                evidence_package_digest_sha256=(retrieval_bundle.evidence_package_digest_sha256),
                corpus_digest_sha256=retrieval_bundle.corpus_digest_sha256,
                embedding_model_id=retrieval_bundle.embedding_model_id,
                embedding_model_revision=retrieval_bundle.embedding_model_revision,
                schema_version=retrieval_bundle.schema_version,
            ),
            sources=tuple(
                MaintenanceSourceProvenanceResponse.model_validate(
                    source,
                    from_attributes=True,
                )
                for source in evidence_package.sources
            ),
        )
