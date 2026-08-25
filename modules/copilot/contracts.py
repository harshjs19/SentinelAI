import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from modules.retriever.models import RetrievalBundle
from shared.evidence.models import EvidencePackage

COPILOT_SCHEMA_VERSION = "1"
PROMPT_POLICY_VERSION = "maintenance_copilot_v1"
VALIDATOR_POLICY_VERSION = "maintenance_safety_v1"

MAX_QUESTION_CHARACTERS = 500
MAX_EXECUTIVE_SUMMARY_CHARACTERS = 700
MAX_FINDING_EXPLANATION_CHARACTERS = 500
MAX_INSPECTION_CONSIDERATION_CHARACTERS = 400
MAX_KNOWLEDGE_GAP_CHARACTERS = 400
MAX_FINDING_EXPLANATIONS = 3
MAX_INSPECTION_CONSIDERATIONS = 3
MAX_CITATIONS_PER_ITEM = 3
MAX_CONTEXT_FINDINGS = 3

_HTML_PATTERN = re.compile(r"<\s*/?\s*[A-Za-z][^>]*>")
_MARKDOWN_LINK_PATTERN = re.compile(r"!?\[[^\]]*]\([^)]*\)")
_URL_PATTERN = re.compile(r"(?i)\b(?:https?://|www\.)\S+")


class CopilotIntent(StrEnum):
    SUMMARIZE_ANALYSIS = "summarize_analysis"
    EXPLAIN_FINDING = "explain_finding"
    EXPLAIN_CONFIDENCE = "explain_confidence"
    INSPECTION_CONSIDERATIONS = "inspection_considerations"
    EXPLAIN_LIMITATIONS = "explain_limitations"


class GenerationStatus(StrEnum):
    GENERATED = "generated"
    DETERMINISTIC = "deterministic"
    FALLBACK = "fallback"


class FallbackReason(StrEnum):
    GENERATION_UNAVAILABLE = "generation_unavailable"
    GENERATION_FAILED = "generation_failed"
    VALIDATION_FAILED = "validation_failed"
    NO_GROUNDED_CONTENT = "no_grounded_content"
    UNSUPPORTED_REQUEST = "unsupported_request"


class RequestDisposition(StrEnum):
    ANSWERED = "answered"
    PARTIALLY_ANSWERED = "partially_answered"
    NOT_SUPPORTED_BY_CURRENT_EVIDENCE = "not_supported_by_current_evidence"


class SafetyViolationCode(StrEnum):
    SCHEMA_INVALID = "schema_invalid"
    CONTENT_LIMIT_EXCEEDED = "content_limit_exceeded"
    INVALID_FINDING_REFERENCE = "invalid_finding_reference"
    UNKNOWN_CITATION = "unknown_citation"
    MISSING_CITATION = "missing_citation"
    INCOMPATIBLE_CITATION = "incompatible_citation"
    UNSUPPORTED_FAULT_CLAIM = "unsupported_fault_claim"
    UNSUPPORTED_PROBABILITY_CLAIM = "unsupported_probability_claim"
    UNSUPPORTED_SEVERITY_CLAIM = "unsupported_severity_claim"
    UNSUPPORTED_HEALTH_OR_RISK_CLAIM = "unsupported_health_or_risk_claim"
    UNSUPPORTED_NUMERIC_CLAIM = "unsupported_numeric_claim"
    HIGH_IMPACT_ACTION = "high_impact_action"
    MODEL_SCOPE_OVERCLAIM = "model_scope_overclaim"
    UNSAFE_MARKUP = "unsafe_markup"
    DETERMINISTIC_FIELD_MISMATCH = "deterministic_field_mismatch"


def normalize_question(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        return None
    if len(normalized) > MAX_QUESTION_CHARACTERS:
        raise ValueError(f"Copilot question cannot exceed {MAX_QUESTION_CHARACTERS} characters")
    if "\x00" in normalized:
        raise ValueError("Copilot question cannot contain NUL")
    if any(
        unicodedata.category(character) == "Cc" and character not in "\t\n\r"
        for character in normalized
    ):
        raise ValueError("Copilot question contains a disallowed control character")
    if _HTML_PATTERN.search(normalized):
        raise ValueError("Copilot question cannot contain HTML")
    if _MARKDOWN_LINK_PATTERN.search(normalized):
        raise ValueError("Copilot question cannot contain Markdown links")
    if _URL_PATTERN.search(normalized):
        raise ValueError("Copilot question cannot contain URLs")
    return normalized


@dataclass(frozen=True)
class MaintenanceCopilotRequest:
    evidence_package: EvidencePackage
    retrieval_bundle: RetrievalBundle
    intent: CopilotIntent
    question: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "question", normalize_question(self.question))


class DraftFindingExplanation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    finding_id: str = Field(min_length=2, max_length=16)
    text: str = Field(min_length=1, max_length=MAX_FINDING_EXPLANATION_CHARACTERS)
    citation_ids: tuple[str, ...] = Field(
        min_length=1,
        max_length=MAX_CITATIONS_PER_ITEM,
    )


class DraftInspectionConsideration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    finding_id: str = Field(min_length=2, max_length=16)
    text: str = Field(min_length=1, max_length=MAX_INSPECTION_CONSIDERATION_CHARACTERS)
    citation_ids: tuple[str, ...] = Field(
        min_length=1,
        max_length=MAX_CITATIONS_PER_ITEM,
    )


class CopilotDraft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    executive_summary: str = Field(
        min_length=1,
        max_length=MAX_EXECUTIVE_SUMMARY_CHARACTERS,
    )
    finding_explanations: tuple[DraftFindingExplanation, ...] = Field(
        default=(),
        max_length=MAX_FINDING_EXPLANATIONS,
    )
    inspection_considerations: tuple[DraftInspectionConsideration, ...] = Field(
        default=(),
        max_length=MAX_INSPECTION_CONSIDERATIONS,
    )
    knowledge_gap_statement: str | None = Field(
        default=None,
        max_length=MAX_KNOWLEDGE_GAP_CHARACTERS,
    )


@dataclass(frozen=True)
class SafetyViolation:
    code: SafetyViolationCode
    location: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    violations: tuple[SafetyViolation, ...]

    def __post_init__(self) -> None:
        if self.valid == bool(self.violations):
            raise ValueError("Validation result validity must agree with its violations")
