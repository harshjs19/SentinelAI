import hashlib
import hmac
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from domain.enums.analysis_limitation import AnalysisLimitation
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from domain.enums.modality import Modality
from domain.enums.risk_level import RiskLevel
from modules.copilot.citations import CopilotCitation
from modules.copilot.context import PreparedCopilotRequest, finding_references
from modules.copilot.contracts import (
    COPILOT_SCHEMA_VERSION,
    PROMPT_POLICY_VERSION,
    VALIDATOR_POLICY_VERSION,
    CopilotDraft,
    CopilotIntent,
    DraftFindingExplanation,
    DraftInspectionConsideration,
    FallbackReason,
    GenerationStatus,
    RequestDisposition,
    SafetyViolation,
    ValidationResult,
)
from modules.copilot.policy import unavailable_claim_explanations
from shared.evidence.canonical import canonical_json_bytes
from shared.evidence.models import (
    EvidenceClaimSupport,
    MachineSnapshot,
    ModelProvenance,
)

MAINTENANCE_REPORT_DISCLAIMER = (
    "This report provides evidence interpretation and source-backed inspection context. "
    "It does not authorize equipment shutdown, continued operation, isolation, repair, "
    "or return to service."
)
FALLBACK_EXECUTIVE_SUMMARY = (
    "The analysis results are available below. A grounded maintenance explanation could "
    "not be generated for this request."
)
FALLBACK_KNOWLEDGE_GAP = "No additional maintenance interpretation is provided."

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class EvidenceReference:
    package_id: str
    package_digest_sha256: str


@dataclass(frozen=True)
class RetrievalReference:
    schema_version: str
    evidence_package_id: str
    evidence_package_digest_sha256: str
    retrieval_bundle_digest_sha256: str
    corpus_digest_sha256: str
    embedding_model_id: str
    embedding_model_revision: str
    collection_name: str


@dataclass(frozen=True)
class ReportFinding:
    finding_id: str
    modality: Modality
    code: str
    condition: ConditionState
    confidence: float
    confidence_kind: ConfidenceKind


@dataclass(frozen=True)
class ReportAnalysis:
    condition: ConditionState
    status: AnalysisStatus
    findings: tuple[ReportFinding, ...]
    health_score: float | None
    risk_level: RiskLevel | None
    claim_support: EvidenceClaimSupport


@dataclass(frozen=True)
class ReportNarrative:
    executive_summary: str
    finding_explanations: tuple[DraftFindingExplanation, ...]
    inspection_considerations: tuple[DraftInspectionConsideration, ...]
    knowledge_gap_statement: str | None


@dataclass(frozen=True)
class ReportLimitations:
    analysis_limitations: tuple[AnalysisLimitation, ...]
    model_scope_limitations: tuple[str, ...]
    unavailable_claims: tuple[str, ...]
    generation_limitations: tuple[str, ...]


@dataclass(frozen=True)
class GenerationProvenance:
    provider: str
    model: str | None
    model_snapshot: str | None
    temperature: float | None
    reasoning_effort: str | None
    schema_version: str
    prompt_policy_version: str
    validator_policy_version: str
    response_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    repair_attempted: bool = False

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("Generation provider cannot be empty")
        for value in (self.input_tokens, self.output_tokens, self.latency_ms):
            if value is not None and (isinstance(value, bool) or value < 0):
                raise ValueError("Generation usage and latency values cannot be negative")


@dataclass(frozen=True)
class SafetyValidationSnapshot:
    valid: bool
    violations: tuple[SafetyViolation, ...]
    validator_policy_version: str
    repair_attempted: bool


@dataclass(frozen=True)
class MaintenanceReport:
    schema_version: str
    report_id: UUID
    report_digest_sha256: str
    generated_at: datetime
    generation_status: GenerationStatus
    fallback_reason: FallbackReason | None
    request_disposition: RequestDisposition
    request_intent: CopilotIntent
    evidence_reference: EvidenceReference
    retrieval_reference: RetrievalReference
    machine: MachineSnapshot
    analysis: ReportAnalysis
    producing_models: tuple[ModelProvenance, ...]
    narrative: ReportNarrative
    limitations: ReportLimitations
    citations: tuple[CopilotCitation, ...]
    generation_provenance: GenerationProvenance
    safety_validation: SafetyValidationSnapshot
    disclaimer: str

    def __post_init__(self) -> None:
        if self.schema_version != COPILOT_SCHEMA_VERSION:
            raise ValueError(f"Maintenance Report schema_version must be {COPILOT_SCHEMA_VERSION}")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() != timedelta(0):
            raise ValueError("Maintenance Report generated_at must be timezone-aware UTC")
        if _SHA256_PATTERN.fullmatch(self.report_digest_sha256) is None:
            raise ValueError("Maintenance Report digest must be a lowercase SHA-256 value")
        if (self.generation_status is GenerationStatus.FALLBACK) != (
            self.fallback_reason is not None
        ):
            raise ValueError("Maintenance Report fallback status and reason are inconsistent")


def fake_generation_provenance(*, repair_attempted: bool = False) -> GenerationProvenance:
    return GenerationProvenance(
        provider="fake",
        model="fake-structured-generator",
        model_snapshot="test-snapshot",
        temperature=0.0,
        reasoning_effort=None,
        schema_version=COPILOT_SCHEMA_VERSION,
        prompt_policy_version=PROMPT_POLICY_VERSION,
        validator_policy_version=VALIDATOR_POLICY_VERSION,
        repair_attempted=repair_attempted,
    )


def fallback_generation_provenance() -> GenerationProvenance:
    return GenerationProvenance(
        provider="deterministic",
        model=None,
        model_snapshot=None,
        temperature=None,
        reasoning_effort=None,
        schema_version=COPILOT_SCHEMA_VERSION,
        prompt_policy_version=PROMPT_POLICY_VERSION,
        validator_policy_version=VALIDATOR_POLICY_VERSION,
    )


def assemble_maintenance_report(
    prepared: PreparedCopilotRequest,
    draft: CopilotDraft,
    generation_provenance: GenerationProvenance,
    validation: ValidationResult,
    *,
    request_disposition: RequestDisposition = RequestDisposition.ANSWERED,
    report_id: UUID | None = None,
    generated_at: datetime | None = None,
) -> MaintenanceReport:
    if not validation.valid:
        raise ValueError("Cannot assemble a generated report from an invalid Copilot draft")
    citations = _used_citations(prepared, draft)
    report = _build_report(
        prepared,
        generation_status=GenerationStatus.GENERATED,
        fallback_reason=None,
        request_disposition=request_disposition,
        narrative=ReportNarrative(
            executive_summary=draft.executive_summary,
            finding_explanations=draft.finding_explanations,
            inspection_considerations=draft.inspection_considerations,
            knowledge_gap_statement=draft.knowledge_gap_statement,
        ),
        citations=citations,
        generation_provenance=generation_provenance,
        validation=validation,
        report_id=report_id or uuid4(),
        generated_at=generated_at or datetime.now(UTC),
    )
    return _with_digest(report)


def assemble_fallback_report(
    prepared: PreparedCopilotRequest,
    fallback_reason: FallbackReason,
    *,
    generation_provenance: GenerationProvenance | None = None,
    request_disposition: RequestDisposition | None = None,
    validation: ValidationResult | None = None,
    report_id: UUID | None = None,
    generated_at: datetime | None = None,
) -> MaintenanceReport:
    disposition = request_disposition or _fallback_disposition(fallback_reason)
    provenance = generation_provenance or fallback_generation_provenance()
    safety = validation or ValidationResult(valid=True, violations=())
    report = _build_report(
        prepared,
        generation_status=GenerationStatus.FALLBACK,
        fallback_reason=fallback_reason,
        request_disposition=disposition,
        narrative=ReportNarrative(
            executive_summary=FALLBACK_EXECUTIVE_SUMMARY,
            finding_explanations=(),
            inspection_considerations=(),
            knowledge_gap_statement=FALLBACK_KNOWLEDGE_GAP,
        ),
        citations=(),
        generation_provenance=provenance,
        validation=safety,
        report_id=report_id or uuid4(),
        generated_at=generated_at or datetime.now(UTC),
    )
    return _with_digest(report)


def verify_report_digest(report: MaintenanceReport) -> bool:
    expected = hashlib.sha256(
        canonical_json_bytes(maintenance_report_core_payload(report))
    ).hexdigest()
    return hmac.compare_digest(report.report_digest_sha256, expected)


def verify_maintenance_report(
    report: MaintenanceReport,
    prepared: PreparedCopilotRequest,
) -> bool:
    request = prepared.request
    package = request.evidence_package
    bundle = request.retrieval_bundle
    if not verify_report_digest(report):
        return False
    if report.evidence_reference != _evidence_reference(prepared):
        return False
    if report.retrieval_reference != _retrieval_reference(prepared):
        return False
    if report.machine != package.machine:
        return False
    if report.analysis != _report_analysis(prepared):
        return False
    if report.producing_models != package.models:
        return False
    if report.request_intent is not request.intent:
        return False
    if report.retrieval_reference.evidence_package_id != bundle.evidence_package_id:
        return False
    if report.generation_status is GenerationStatus.FALLBACK:
        return (
            report.citations == ()
            and report.narrative.finding_explanations == ()
            and report.narrative.inspection_considerations == ()
            and report.narrative.executive_summary == FALLBACK_EXECUTIVE_SUMMARY
            and report.narrative.knowledge_gap_statement == FALLBACK_KNOWLEDGE_GAP
        )
    expected_citations = _used_citations_from_narrative(prepared, report.narrative)
    return report.citations == expected_citations


def maintenance_report_payload(report: MaintenanceReport) -> dict[str, object]:
    payload = maintenance_report_core_payload(report)
    payload["report_digest_sha256"] = report.report_digest_sha256
    return payload


def maintenance_report_core_payload(report: MaintenanceReport) -> dict[str, object]:
    return {
        "schema_version": report.schema_version,
        "report_id": report.report_id,
        "generated_at": report.generated_at,
        "generation_status": report.generation_status,
        "fallback_reason": report.fallback_reason,
        "request_disposition": report.request_disposition,
        "request_intent": report.request_intent,
        "evidence_reference": {
            "package_id": report.evidence_reference.package_id,
            "package_digest_sha256": report.evidence_reference.package_digest_sha256,
        },
        "retrieval_reference": {
            "schema_version": report.retrieval_reference.schema_version,
            "evidence_package_id": report.retrieval_reference.evidence_package_id,
            "evidence_package_digest_sha256": (
                report.retrieval_reference.evidence_package_digest_sha256
            ),
            "retrieval_bundle_digest_sha256": (
                report.retrieval_reference.retrieval_bundle_digest_sha256
            ),
            "corpus_digest_sha256": report.retrieval_reference.corpus_digest_sha256,
            "embedding_model_id": report.retrieval_reference.embedding_model_id,
            "embedding_model_revision": report.retrieval_reference.embedding_model_revision,
            "collection_name": report.retrieval_reference.collection_name,
        },
        "machine": {
            "machine_id": report.machine.machine_id,
            "name": report.machine.name,
            "asset_type": report.machine.asset_type,
        },
        "analysis": _report_analysis_payload(report.analysis),
        "producing_models": [_model_payload(model) for model in report.producing_models],
        "narrative": _narrative_payload(report.narrative),
        "limitations": {
            "analysis_limitations": list(report.limitations.analysis_limitations),
            "model_scope_limitations": list(report.limitations.model_scope_limitations),
            "unavailable_claims": list(report.limitations.unavailable_claims),
            "generation_limitations": list(report.limitations.generation_limitations),
        },
        "citations": [_citation_payload(citation) for citation in report.citations],
        "generation_provenance": _generation_provenance_payload(report.generation_provenance),
        "safety_validation": {
            "valid": report.safety_validation.valid,
            "violations": [
                {
                    "code": violation.code,
                    "location": violation.location,
                    "message": violation.message,
                }
                for violation in report.safety_validation.violations
            ],
            "validator_policy_version": report.safety_validation.validator_policy_version,
            "repair_attempted": report.safety_validation.repair_attempted,
        },
        "disclaimer": report.disclaimer,
    }


def _build_report(
    prepared: PreparedCopilotRequest,
    *,
    generation_status: GenerationStatus,
    fallback_reason: FallbackReason | None,
    request_disposition: RequestDisposition,
    narrative: ReportNarrative,
    citations: tuple[CopilotCitation, ...],
    generation_provenance: GenerationProvenance,
    validation: ValidationResult,
    report_id: UUID,
    generated_at: datetime,
) -> MaintenanceReport:
    return MaintenanceReport(
        schema_version=COPILOT_SCHEMA_VERSION,
        report_id=report_id,
        report_digest_sha256="0" * 64,
        generated_at=generated_at,
        generation_status=generation_status,
        fallback_reason=fallback_reason,
        request_disposition=request_disposition,
        request_intent=prepared.request.intent,
        evidence_reference=_evidence_reference(prepared),
        retrieval_reference=_retrieval_reference(prepared),
        machine=prepared.request.evidence_package.machine,
        analysis=_report_analysis(prepared),
        producing_models=prepared.request.evidence_package.models,
        narrative=narrative,
        limitations=_report_limitations(prepared, generation_status),
        citations=citations,
        generation_provenance=generation_provenance,
        safety_validation=SafetyValidationSnapshot(
            valid=validation.valid,
            violations=validation.violations,
            validator_policy_version=VALIDATOR_POLICY_VERSION,
            repair_attempted=generation_provenance.repair_attempted,
        ),
        disclaimer=MAINTENANCE_REPORT_DISCLAIMER,
    )


def _with_digest(report: MaintenanceReport) -> MaintenanceReport:
    digest = hashlib.sha256(
        canonical_json_bytes(maintenance_report_core_payload(report))
    ).hexdigest()
    return replace(report, report_digest_sha256=digest)


def _evidence_reference(prepared: PreparedCopilotRequest) -> EvidenceReference:
    package = prepared.request.evidence_package
    return EvidenceReference(package.package_id, package.package_digest_sha256)


def _retrieval_reference(prepared: PreparedCopilotRequest) -> RetrievalReference:
    bundle = prepared.request.retrieval_bundle
    return RetrievalReference(
        schema_version=bundle.schema_version,
        evidence_package_id=bundle.evidence_package_id,
        evidence_package_digest_sha256=bundle.evidence_package_digest_sha256,
        retrieval_bundle_digest_sha256=bundle.retrieval_bundle_digest_sha256,
        corpus_digest_sha256=bundle.corpus_digest_sha256,
        embedding_model_id=bundle.embedding_model_id,
        embedding_model_revision=bundle.embedding_model_revision,
        collection_name=bundle.collection_name,
    )


def _report_analysis(prepared: PreparedCopilotRequest) -> ReportAnalysis:
    package = prepared.request.evidence_package
    finding_ids = {id(finding): finding_id for finding_id, finding in finding_references(package)}
    findings = tuple(
        ReportFinding(
            finding_id=finding_ids[id(finding)],
            modality=finding.modality,
            code=finding.code,
            condition=finding.condition,
            confidence=finding.confidence,
            confidence_kind=finding.confidence_kind,
        )
        for finding in package.analysis.findings
    )
    return ReportAnalysis(
        condition=package.analysis.condition,
        status=package.analysis.status,
        findings=findings,
        health_score=package.analysis.health_score,
        risk_level=package.analysis.risk_level,
        claim_support=package.claim_support,
    )


def _report_limitations(
    prepared: PreparedCopilotRequest,
    generation_status: GenerationStatus,
) -> ReportLimitations:
    return ReportLimitations(
        analysis_limitations=prepared.request.evidence_package.analysis.limitations,
        model_scope_limitations=tuple(
            f"{model.modality.value}: {model.status.value}; validated scope: "
            f"{model.validated_scope}"
            for model in prepared.request.evidence_package.models
        ),
        unavailable_claims=unavailable_claim_explanations(prepared),
        generation_limitations=(
            ("Grounded maintenance narrative was not generated.",)
            if generation_status is GenerationStatus.FALLBACK
            else ()
        ),
    )


def _used_citations(
    prepared: PreparedCopilotRequest,
    draft: CopilotDraft,
) -> tuple[CopilotCitation, ...]:
    narrative = ReportNarrative(
        executive_summary=draft.executive_summary,
        finding_explanations=draft.finding_explanations,
        inspection_considerations=draft.inspection_considerations,
        knowledge_gap_statement=draft.knowledge_gap_statement,
    )
    return _used_citations_from_narrative(prepared, narrative)


def _used_citations_from_narrative(
    prepared: PreparedCopilotRequest,
    narrative: ReportNarrative,
) -> tuple[CopilotCitation, ...]:
    used = {
        citation_id
        for item in narrative.finding_explanations + narrative.inspection_considerations
        for citation_id in item.citation_ids
    }
    return tuple(
        item.citation for item in prepared.assigned_citations if item.citation.citation_id in used
    )


def _fallback_disposition(reason: FallbackReason) -> RequestDisposition:
    if reason in (FallbackReason.NO_GROUNDED_CONTENT, FallbackReason.UNSUPPORTED_REQUEST):
        return RequestDisposition.NOT_SUPPORTED_BY_CURRENT_EVIDENCE
    return RequestDisposition.PARTIALLY_ANSWERED


def _report_analysis_payload(analysis: ReportAnalysis) -> dict[str, object]:
    return {
        "condition": analysis.condition,
        "status": analysis.status,
        "findings": [
            {
                "finding_id": finding.finding_id,
                "modality": finding.modality,
                "code": finding.code,
                "condition": finding.condition,
                "confidence": finding.confidence,
                "confidence_kind": finding.confidence_kind,
            }
            for finding in analysis.findings
        ],
        "health_score": analysis.health_score,
        "risk_level": analysis.risk_level,
        "claim_support": {
            "condition_available": analysis.claim_support.condition_available,
            "failure_probability_available": analysis.claim_support.failure_probability_available,
            "fault_severity_available": analysis.claim_support.fault_severity_available,
            "health_score_available": analysis.claim_support.health_score_available,
            "operational_risk_available": analysis.claim_support.operational_risk_available,
        },
    }


def _model_payload(model: ModelProvenance) -> dict[str, object]:
    return {
        "model_id": model.model_id,
        "modality": model.modality,
        "status": model.status,
        "runtime_default": model.runtime_default,
        "validated_scope": model.validated_scope,
        "evaluation_reference": model.evaluation_reference,
        "confidence_semantics": model.confidence_semantics,
    }


def _narrative_payload(narrative: ReportNarrative) -> dict[str, object]:
    return {
        "executive_summary": narrative.executive_summary,
        "finding_explanations": [
            item.model_dump(mode="python") for item in narrative.finding_explanations
        ],
        "inspection_considerations": [
            item.model_dump(mode="python") for item in narrative.inspection_considerations
        ],
        "knowledge_gap_statement": narrative.knowledge_gap_statement,
    }


def _citation_payload(citation: CopilotCitation) -> dict[str, object]:
    return {
        "citation_id": citation.citation_id,
        "chunk_id": citation.chunk_id,
        "source_id": citation.source_id,
        "source_digest_sha256": citation.source_digest_sha256,
        "title": citation.title,
        "publisher": citation.publisher,
        "section": citation.section,
        "source_uri": citation.source_uri,
        "fault_code": citation.fault_code,
        "asset_type": citation.asset_type,
        "matched_intent": citation.matched_intent,
        "source_lane": citation.source_lane,
    }


def _generation_provenance_payload(provenance: GenerationProvenance) -> dict[str, object]:
    return {
        "provider": provenance.provider,
        "model": provenance.model,
        "model_snapshot": provenance.model_snapshot,
        "temperature": provenance.temperature,
        "reasoning_effort": provenance.reasoning_effort,
        "schema_version": provenance.schema_version,
        "prompt_policy_version": provenance.prompt_policy_version,
        "validator_policy_version": provenance.validator_policy_version,
        "response_id": provenance.response_id,
        "input_tokens": provenance.input_tokens,
        "output_tokens": provenance.output_tokens,
        "latency_ms": provenance.latency_ms,
        "repair_attempted": provenance.repair_attempted,
    }
