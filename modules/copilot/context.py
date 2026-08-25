from dataclasses import dataclass

from ai_core.model_capabilities import ModelLifecycleStatus
from domain.entities.finding import Finding
from domain.enums.analysis_limitation import AnalysisLimitation
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from domain.enums.modality import Modality
from modules.copilot.citations import (
    AssignedCitation,
    ProviderCitationContext,
    assign_citations,
)
from modules.copilot.contracts import MAX_CONTEXT_FINDINGS, CopilotIntent, MaintenanceCopilotRequest
from shared.evidence.models import EvidenceClaimSupport, EvidencePackage


@dataclass(frozen=True)
class ContextFinding:
    finding_id: str
    modality: Modality
    code: str
    condition: ConditionState
    confidence_kind: ConfidenceKind
    confidence_semantics: str
    model_status: ModelLifecycleStatus
    validated_scope: str


@dataclass(frozen=True)
class ContextModel:
    modality: Modality
    status: ModelLifecycleStatus
    validated_scope: str
    confidence_semantics: str


@dataclass(frozen=True)
class ContextClaimSupport:
    condition_available: bool
    failure_probability_available: bool
    fault_severity_available: bool
    health_score_available: bool
    operational_risk_available: bool


@dataclass(frozen=True)
class CopilotGenerationContext:
    asset_type: str
    condition: ConditionState
    analysis_status: AnalysisStatus
    findings: tuple[ContextFinding, ...]
    models: tuple[ContextModel, ...]
    limitations: tuple[AnalysisLimitation, ...]
    claim_support: ContextClaimSupport
    citations: tuple[ProviderCitationContext, ...]
    intent: CopilotIntent
    question: str | None


@dataclass(frozen=True)
class PreparedCopilotRequest:
    request: MaintenanceCopilotRequest
    context: CopilotGenerationContext
    assigned_citations: tuple[AssignedCitation, ...]


class CopilotContextBuilder:
    def build(self, request: MaintenanceCopilotRequest) -> PreparedCopilotRequest:
        assigned = assign_citations(request)
        package = request.evidence_package
        models_by_modality = {model.modality: model for model in package.models}
        finding_pairs = finding_references(package)[:MAX_CONTEXT_FINDINGS]
        findings = tuple(
            ContextFinding(
                finding_id=finding_id,
                modality=finding.modality,
                code=finding.code,
                condition=finding.condition,
                confidence_kind=finding.confidence_kind,
                confidence_semantics=models_by_modality[finding.modality].confidence_semantics,
                model_status=models_by_modality[finding.modality].status,
                validated_scope=models_by_modality[finding.modality].validated_scope,
            )
            for finding_id, finding in finding_pairs
        )
        context = CopilotGenerationContext(
            asset_type=package.machine.asset_type,
            condition=package.analysis.condition,
            analysis_status=package.analysis.status,
            findings=findings,
            models=tuple(
                ContextModel(
                    modality=model.modality,
                    status=model.status,
                    validated_scope=model.validated_scope,
                    confidence_semantics=model.confidence_semantics,
                )
                for model in package.models
            ),
            limitations=package.analysis.limitations,
            claim_support=_context_claim_support(package.claim_support),
            citations=tuple(item.provider_context for item in assigned),
            intent=request.intent,
            question=request.question,
        )
        return PreparedCopilotRequest(request, context, assigned)


def finding_references(package: EvidencePackage) -> tuple[tuple[str, Finding], ...]:
    ordered = list(package.analysis.top_findings)
    for finding in package.analysis.findings:
        if not any(finding is selected for selected in ordered):
            ordered.append(finding)
    return tuple((f"F{index}", finding) for index, finding in enumerate(ordered, start=1))


def generation_context_payload(context: CopilotGenerationContext) -> dict[str, object]:
    return {
        "asset_type": context.asset_type,
        "condition": context.condition,
        "analysis_status": context.analysis_status,
        "findings": [
            {
                "finding_id": finding.finding_id,
                "modality": finding.modality,
                "code": finding.code,
                "condition": finding.condition,
                "confidence_kind": finding.confidence_kind,
                "confidence_semantics": finding.confidence_semantics,
                "model_status": finding.model_status,
                "validated_scope": finding.validated_scope,
            }
            for finding in context.findings
        ],
        "models": [
            {
                "modality": model.modality,
                "status": model.status,
                "validated_scope": model.validated_scope,
                "confidence_semantics": model.confidence_semantics,
            }
            for model in context.models
        ],
        "limitations": list(context.limitations),
        "claim_support": {
            "condition_available": context.claim_support.condition_available,
            "failure_probability_available": (context.claim_support.failure_probability_available),
            "fault_severity_available": context.claim_support.fault_severity_available,
            "health_score_available": context.claim_support.health_score_available,
            "operational_risk_available": context.claim_support.operational_risk_available,
        },
        "citations": [
            {
                "citation_id": citation.citation_id,
                "title": citation.title,
                "publisher": citation.publisher,
                "section": citation.section,
                "fault_code": citation.fault_code,
                "asset_type": citation.asset_type,
                "source_lane": citation.source_lane,
                "text": citation.text,
            }
            for citation in context.citations
        ],
        "intent": context.intent,
        "question": context.question,
    }


def _context_claim_support(support: EvidenceClaimSupport) -> ContextClaimSupport:
    return ContextClaimSupport(
        condition_available=support.condition_available,
        failure_probability_available=support.failure_probability_available,
        fault_severity_available=support.fault_severity_available,
        health_score_available=support.health_score_available,
        operational_risk_available=support.operational_risk_available,
    )
