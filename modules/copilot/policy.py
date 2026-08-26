import re
from dataclasses import dataclass

from domain.enums.analysis_limitation import AnalysisLimitation
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from modules.copilot.context import PreparedCopilotRequest
from modules.copilot.contracts import CopilotIntent, FallbackReason, RequestDisposition
from modules.retriever.models import RetrievalLane

_ACTOR = r"(?:i|we|you)"
_EQUIPMENT = r"(?:it|(?:(?:this|that|the)\s+)?(?:machine|motor|equipment))"
_REPLACEABLE = rf"(?:{_EQUIPMENT}|(?:(?:this|that|the)\s+)?(?:bearing|component))"
_MODAL_ACTOR_PREFIX = rf"(?:(?:should|can|could|may|must)\s+{_ACTOR}\s+)?"
_OPERATIONAL_END = r"(?:\s+(?:now|immediately))?\s*[?.!]*$"

_HIGH_IMPACT_OPERATIONAL_PATTERNS = (
    # "shut down the machine" and separable "shut the machine down" phrasal forms.
    rf"^\s*{_MODAL_ACTOR_PREFIX}(?:shut\s+down(?:\s+{_EQUIPMENT})?|"
    rf"shut\s+{_EQUIPMENT}\s+down){_OPERATIONAL_END}",
    rf"^\s*{_MODAL_ACTOR_PREFIX}stop(?:\s+(?:the\s+)?(?:machine|motor|equipment|operation))?"
    rf"{_OPERATIONAL_END}",
    # Continued-operation authority, including explicit safety-to-operate questions.
    rf"^\s*(?:(?:should|can|could|may)\s+{_ACTOR}\s+|is\s+it\s+safe\s+to\s+)?"
    rf"(?:keep\s+(?:operating|running)(?:\s+{_EQUIPMENT})?|"
    rf"continue\s+(?:operating|running)(?:\s+{_EQUIPMENT})?|operate|run|continue)"
    rf"{_OPERATIONAL_END}",
    # Restart and return-to-service authorization.
    rf"^\s*{_MODAL_ACTOR_PREFIX}(?:restart(?:\s+{_EQUIPMENT})?|"
    rf"start\s+{_EQUIPMENT}\s+again|return(?:\s+{_EQUIPMENT})?\s+to\s+service)"
    rf"{_OPERATIONAL_END}",
    # Isolation, lockout/tagout, and de-energization instructions.
    rf"^\s*{_MODAL_ACTOR_PREFIX}(?:isolate\s+{_EQUIPMENT}|"
    rf"lock(?:\s+out\s+{_EQUIPMENT}|\s+{_EQUIPMENT}\s+out)|"
    rf"lockout\s+{_EQUIPMENT}|tag(?:\s+out\s+{_EQUIPMENT}|\s+{_EQUIPMENT}\s+out)|"
    rf"tagout\s+{_EQUIPMENT}|de-?energize\s+{_EQUIPMENT}){_OPERATIONAL_END}",
    # Replacement/disposal decisions remain outside V1 authority.
    rf"^\s*{_MODAL_ACTOR_PREFIX}(?:replace\s+{_REPLACEABLE}|discard\s+{_REPLACEABLE}|"
    rf"evacuate(?:\s+(?:the\s+)?(?:area|machine|equipment))?){_OPERATIONAL_END}",
    # Explicit repair urgency is an operational decision even without a named asset.
    r"^\s*(?:must\s+repair(?:\s+(?:it|the\s+(?:machine|motor|equipment)))?\s+now|"
    r"urgent\s+repair)\s*[?.!]*$",
)

_UNSUPPORTED_QUESTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        *_HIGH_IMPACT_OPERATIONAL_PATTERNS,
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
