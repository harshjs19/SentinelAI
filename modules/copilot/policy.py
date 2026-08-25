import re
from dataclasses import dataclass

from domain.enums.analysis_limitation import AnalysisLimitation
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from modules.copilot.context import PreparedCopilotRequest
from modules.copilot.contracts import CopilotIntent, FallbackReason, RequestDisposition
from modules.retriever.models import RetrievalLane

_UNSUPPORTED_QUESTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bshut\s*down\b",
        r"\bstop (?:the )?(?:machine|operation)\b",
        r"\bcontinue operat(?:e|ing|ion)\b",
        r"\brestart\b",
        r"\breturn to service\b",
        r"\block\s*out\b|\btag\s*out\b|\blockout\b|\btagout\b",
        r"\bde-?energize\b|\bisolate (?:the )?(?:machine|equipment)\b",
        r"\breplace\b|\bdiscard\b|\bevacuate\b",
        r"\b(?:chance|likelihood|probability)\b.{0,40}\b(?:fail|fails|failure|breakdown)\b",
        r"\bremaining useful life\b|\bRUL\b|\btime to failure\b",
        r"\b(?:safe|unsafe) to (?:operate|run|continue)\b",
        r"\b(?:what is|assess|calculate|determine) (?:the )?(?:risk|severity|health score)\b",
        r"\bwork order\b",
        r"\bignore (?:all |the )?(?:prior|previous|system) (?:rules|instructions|prompt)\b",
    )
)

_CONFIDENCE_TEMPLATES = {
    "raw_selected_class_predict_proba": (
        "This value is the classifier's selected-class score and is not a validated "
        "machine failure probability."
    ),
    "bounded_empirical_anomaly_evidence_from_normal_calibration": (
        "This value represents bounded acoustic-anomaly evidence relative to the model's "
        "normal calibration distribution and is not a failure probability."
    ),
    "bounded_empirical_visual_anomaly_evidence_from_normal_calibration": (
        "This value represents bounded visual-anomaly evidence relative to the model's "
        "normal calibration distribution and is not a failure probability."
    ),
}

_LIMITATION_TEMPLATES = {
    AnalysisLimitation.UNCALIBRATED_CONFIDENCE: (
        "Model confidence is not calibrated as a machine failure probability."
    ),
    AnalysisLimitation.FAULT_SEVERITY_UNAVAILABLE: (
        "The current analysis does not provide fault severity."
    ),
    AnalysisLimitation.RISK_CONTEXT_UNAVAILABLE: (
        "The current analysis does not provide operational risk context."
    ),
    AnalysisLimitation.SINGLE_MODALITY_EVIDENCE: (
        "The condition is based on evidence from a single sensing modality."
    ),
}


@dataclass(frozen=True)
class RequestPolicyDecision:
    provider_required: bool
    disposition: RequestDisposition
    fallback_reason: FallbackReason | None
    deterministic_explanations: tuple[str, ...] = ()


def explain_confidence_semantics(semantics: str) -> str:
    try:
        return _CONFIDENCE_TEMPLATES[semantics]
    except KeyError as error:
        raise ValueError("Unsupported confidence semantics") from error


def explain_analysis_limitation(limitation: AnalysisLimitation) -> str:
    return _LIMITATION_TEMPLATES[limitation]


def unavailable_claim_explanations(prepared: PreparedCopilotRequest) -> tuple[str, ...]:
    support = prepared.context.claim_support
    explanations: list[str] = []
    if not support.condition_available:
        explanations.append("Machine condition is unavailable from the current evidence.")
    if not support.failure_probability_available:
        explanations.append("Machine failure probability is unavailable.")
    if not support.fault_severity_available:
        explanations.append("Fault severity is unavailable.")
    if not support.health_score_available:
        explanations.append("Health score is unavailable.")
    if not support.operational_risk_available:
        explanations.append("Operational risk is unavailable.")
    return tuple(explanations)


def decide_request_policy(prepared: PreparedCopilotRequest) -> RequestPolicyDecision:
    context = prepared.context
    if context.question and any(
        pattern.search(context.question) for pattern in _UNSUPPORTED_QUESTION_PATTERNS
    ):
        return RequestPolicyDecision(
            provider_required=False,
            disposition=RequestDisposition.NOT_SUPPORTED_BY_CURRENT_EVIDENCE,
            fallback_reason=FallbackReason.UNSUPPORTED_REQUEST,
        )

    if context.intent is CopilotIntent.EXPLAIN_CONFIDENCE:
        explanations = tuple(
            explain_confidence_semantics(model.confidence_semantics) for model in context.models
        )
        return RequestPolicyDecision(
            provider_required=False,
            disposition=(
                RequestDisposition.ANSWERED
                if explanations
                else RequestDisposition.NOT_SUPPORTED_BY_CURRENT_EVIDENCE
            ),
            fallback_reason=(None if explanations else FallbackReason.NO_GROUNDED_CONTENT),
            deterministic_explanations=explanations,
        )

    if context.intent is CopilotIntent.EXPLAIN_LIMITATIONS:
        explanations = tuple(
            explain_analysis_limitation(limitation) for limitation in context.limitations
        ) + unavailable_claim_explanations(prepared)
        return RequestPolicyDecision(
            provider_required=False,
            disposition=RequestDisposition.ANSWERED,
            fallback_reason=None,
            deterministic_explanations=explanations,
        )

    if (
        context.analysis_status is AnalysisStatus.INSUFFICIENT_EVIDENCE
        or not context.claim_support.condition_available
    ):
        return RequestPolicyDecision(
            provider_required=False,
            disposition=RequestDisposition.NOT_SUPPORTED_BY_CURRENT_EVIDENCE,
            fallback_reason=FallbackReason.NO_GROUNDED_CONTENT,
            deterministic_explanations=(
                "The current analysis contains insufficient evidence for a fault-specific "
                "maintenance explanation.",
            ),
        )

    if (
        context.intent is CopilotIntent.INSPECTION_CONSIDERATIONS
        and context.condition is ConditionState.NORMAL
    ):
        return RequestPolicyDecision(
            provider_required=False,
            disposition=RequestDisposition.NOT_SUPPORTED_BY_CURRENT_EVIDENCE,
            fallback_reason=FallbackReason.NO_GROUNDED_CONTENT,
        )

    grounded = _has_grounded_content(prepared)
    return RequestPolicyDecision(
        provider_required=grounded,
        disposition=(
            RequestDisposition.ANSWERED
            if grounded
            else RequestDisposition.NOT_SUPPORTED_BY_CURRENT_EVIDENCE
        ),
        fallback_reason=None if grounded else FallbackReason.NO_GROUNDED_CONTENT,
    )


def _has_grounded_content(prepared: PreparedCopilotRequest) -> bool:
    context = prepared.context
    if context.intent is CopilotIntent.SUMMARIZE_ANALYSIS:
        return bool(context.citations)
    finding_codes = {finding.code for finding in context.findings}
    if context.intent is CopilotIntent.EXPLAIN_FINDING:
        return any(citation.fault_code in finding_codes for citation in context.citations)
    if context.intent is CopilotIntent.INSPECTION_CONSIDERATIONS:
        return any(
            citation.source_lane is RetrievalLane.MAINTENANCE
            and citation.fault_code in finding_codes
            for citation in context.citations
        )
    return False
