import re
from collections.abc import Iterable

from pydantic import ValidationError

from modules.copilot.context import PreparedCopilotRequest
from modules.copilot.contracts import (
    MAX_EXECUTIVE_SUMMARY_CHARACTERS,
    MAX_FINDING_EXPLANATION_CHARACTERS,
    MAX_FINDING_EXPLANATIONS,
    MAX_INSPECTION_CONSIDERATION_CHARACTERS,
    MAX_INSPECTION_CONSIDERATIONS,
    MAX_KNOWLEDGE_GAP_CHARACTERS,
    CopilotDraft,
    SafetyViolation,
    SafetyViolationCode,
    ValidationResult,
)
from modules.retriever.models import RetrievalLane

_FAULT_FAMILIES = {
    "bearing": ("bearing fault", "bearing-related", "bearing related", "bearing_fault"),
    "coupling": ("coupling fault", "coupling_fault"),
    "bent_shaft": ("bent shaft", "bent_shaft"),
    "eccentric_rotor": ("eccentric rotor", "eccentric_rotor", "rotor eccentricity"),
    "imbalance": ("imbalance", "unbalance"),
    "misalignment": ("misalignment", "misaligned"),
    "broken_rotor_bar": (
        "broken rotor bar",
        "half broken rotor bar",
        "broken_rotor_bar",
        "half_broken_rotor_bar",
        "rotor bar fault",
    ),
    "gear_wear": ("gear wear", "gear_wear_25", "gear_wear_50", "gear_wear_75"),
}

_CODE_FAMILY = {
    "bearing_fault": "bearing",
    "coupling_fault": "coupling",
    "bent_shaft": "bent_shaft",
    "eccentric_rotor": "eccentric_rotor",
    "imbalance": "imbalance",
    "misalignment": "misalignment",
    "half_broken_rotor_bar": "broken_rotor_bar",
    "broken_rotor_bar": "broken_rotor_bar",
    "gear_wear_25": "gear_wear",
    "gear_wear_50": "gear_wear",
    "gear_wear_75": "gear_wear",
}

_UNSAFE_MARKUP = re.compile(
    r"(?is)!?\[[^\]]*]\([^)]*\)|https?://|www\.|<\s*/?\s*[A-Za-z][^>]*>|```|<script"
)
_PROBABILITY = re.compile(
    r"(?i)\b(?:failure probability|probability of failure|chance of (?:failure|breakdown)|"
    r"likelihood of (?:failure|breakdown)|percent chance)\b|\b\d+(?:\.\d+)?\s*%"
)
_SEVERITY = re.compile(
    r"(?i)\b(?:severe|critical|minor|moderate|catastrophic|high[- ]severity|low[- ]severity)\b"
)
_HEALTH_RISK = re.compile(
    r"(?i)\b(?:health score|poor health|good health|high risk|low risk|critical risk|"
    r"operational risk|safe to operate|unsafe to operate|remaining useful life|RUL|"
    r"time to failure|hours remaining|days remaining|weeks remaining|life expectancy)\b"
)
_NUMERIC_TECHNICAL = re.compile(
    r"(?i)(?:\b\d+(?:\.\d+)?\s*%|\b\d+(?:\.\d+)?\s*(?:mm|cm|m|°?c|°?f|rpm|"
    r"hz|khz|v|a|w|kw|hours?|days?|weeks?|months?|years?)\b|\b0\.\d+\b)"
)
_HIGH_IMPACT = re.compile(
    r"(?i)\b(?:shutdown|shut down|stop (?:the )?(?:machine|operation)|continue operating|"
    r"restart|return to service|lock\s*out|tag\s*out|lockout|tagout|de-?energize|"
    r"isolate (?:the )?(?:machine|equipment)|evacuate|replace(?: the| component)?|discard|"
    r"bypass protection|disable alarm|must|immediately|urgent|as soon as possible)\b"
)
_MODEL_OVERCLAIM = re.compile(
    r"(?i)\b(?:universally validated|production validated|proven across machines|"
    r"guaranteed|guarantees|"
    r"always detects|reliably detects all|industry-wide validation)\b"
)
_SAFE_INSPECTION_LANGUAGE = re.compile(
    r"(?i)\b(?:inspection (?:could consider|may examine)|could be inspected|"
    r"area(?:s)? for inspection|reference material identifies)\b"
)
_INSPECTION_DIRECTIVE = re.compile(r"(?i)(?:^|[.!?]\s*)inspect\b|\byou (?:should|must) inspect\b")


class MaintenanceSafetyValidator:
    """Conservative lexical and structural guard for future generated Copilot drafts."""

    def validate(
        self,
        draft_input: CopilotDraft | object,
        prepared: PreparedCopilotRequest,
    ) -> ValidationResult:
        try:
            draft = (
                draft_input
                if isinstance(draft_input, CopilotDraft)
                else CopilotDraft.model_validate(draft_input)
            )
        except (ValidationError, TypeError, ValueError):
            return ValidationResult(
                valid=False,
                violations=(
                    SafetyViolation(
                        SafetyViolationCode.SCHEMA_INVALID,
                        "draft",
                        "Draft does not match the Copilot schema",
                    ),
                ),
            )

        violations: list[SafetyViolation] = []
        self._validate_limits(draft, violations)
        self._validate_items(draft, prepared, violations)
        self._validate_generated_text(draft, prepared, violations)
        return ValidationResult(valid=not violations, violations=tuple(violations))

    def _validate_limits(
        self,
        draft: CopilotDraft,
        violations: list[SafetyViolation],
    ) -> None:
        limits = (
            ("executive_summary", draft.executive_summary, MAX_EXECUTIVE_SUMMARY_CHARACTERS),
            (
                "knowledge_gap_statement",
                draft.knowledge_gap_statement or "",
                MAX_KNOWLEDGE_GAP_CHARACTERS,
            ),
        )
        for location, value, maximum in limits:
            if len(value) > maximum:
                _add(
                    violations,
                    SafetyViolationCode.CONTENT_LIMIT_EXCEEDED,
                    location,
                    "Generated content exceeds the allowed limit",
                )
        if len(draft.finding_explanations) > MAX_FINDING_EXPLANATIONS:
            _add(
                violations,
                SafetyViolationCode.CONTENT_LIMIT_EXCEEDED,
                "finding_explanations",
                "Too many finding explanations",
            )
        if len(draft.inspection_considerations) > MAX_INSPECTION_CONSIDERATIONS:
            _add(
                violations,
                SafetyViolationCode.CONTENT_LIMIT_EXCEEDED,
                "inspection_considerations",
                "Too many inspection considerations",
            )
        for index, item in enumerate(draft.finding_explanations):
            if len(item.text) > MAX_FINDING_EXPLANATION_CHARACTERS:
                _add(
                    violations,
                    SafetyViolationCode.CONTENT_LIMIT_EXCEEDED,
                    f"finding_explanations.{index}.text",
                    "Finding explanation exceeds the allowed limit",
                )
        for index, item in enumerate(draft.inspection_considerations):
            if len(item.text) > MAX_INSPECTION_CONSIDERATION_CHARACTERS:
                _add(
                    violations,
                    SafetyViolationCode.CONTENT_LIMIT_EXCEEDED,
                    f"inspection_considerations.{index}.text",
                    "Inspection consideration exceeds the allowed limit",
                )

    def _validate_items(
        self,
        draft: CopilotDraft,
        prepared: PreparedCopilotRequest,
        violations: list[SafetyViolation],
    ) -> None:
        findings = {finding.finding_id: finding for finding in prepared.context.findings}
        citations = {
            assigned.citation.citation_id: assigned.citation
            for assigned in prepared.assigned_citations
        }
        seen_explanations: set[str] = set()
        for index, item in enumerate(draft.finding_explanations):
            location = f"finding_explanations.{index}"
            if item.finding_id in seen_explanations:
                _add(
                    violations,
                    SafetyViolationCode.INVALID_FINDING_REFERENCE,
                    f"{location}.finding_id",
                    "A finding can have at most one explanation",
                )
            seen_explanations.add(item.finding_id)
            finding = findings.get(item.finding_id)
            if finding is None:
                _add(
                    violations,
                    SafetyViolationCode.INVALID_FINDING_REFERENCE,
                    f"{location}.finding_id",
                    "Finding reference is not available in this request",
                )
            self._validate_citations(
                item.citation_ids,
                location,
                finding.code if finding else None,
                prepared.context.asset_type,
                citations,
                maintenance_required=False,
                violations=violations,
            )

        seen_considerations: set[str] = set()
        for index, item in enumerate(draft.inspection_considerations):
            location = f"inspection_considerations.{index}"
            if item.finding_id in seen_considerations:
                _add(
                    violations,
                    SafetyViolationCode.INVALID_FINDING_REFERENCE,
                    f"{location}.finding_id",
                    "A finding can have at most one inspection consideration",
                )
            seen_considerations.add(item.finding_id)
            finding = findings.get(item.finding_id)
            if finding is None:
                _add(
                    violations,
                    SafetyViolationCode.INVALID_FINDING_REFERENCE,
                    f"{location}.finding_id",
                    "Finding reference is not available in this request",
                )
            self._validate_citations(
                item.citation_ids,
                location,
                finding.code if finding else None,
                prepared.context.asset_type,
                citations,
                maintenance_required=True,
                violations=violations,
            )

    def _validate_citations(
        self,
        citation_ids: tuple[str, ...],
        location: str,
        finding_code: str | None,
        asset_type: str,
        citations: dict[str, object],
        *,
        maintenance_required: bool,
        violations: list[SafetyViolation],
    ) -> None:
        if not citation_ids:
            _add(
                violations,
                SafetyViolationCode.MISSING_CITATION,
                f"{location}.citation_ids",
                "Generated technical content requires a citation",
            )
            return
        if len(set(citation_ids)) != len(citation_ids):
            _add(
                violations,
                SafetyViolationCode.INCOMPATIBLE_CITATION,
                f"{location}.citation_ids",
                "Duplicate citation IDs are not allowed",
            )
        for citation_id in citation_ids:
            citation = citations.get(citation_id)
            if citation is None:
                _add(
                    violations,
                    SafetyViolationCode.UNKNOWN_CITATION,
                    f"{location}.citation_ids",
                    "Citation ID is not available in this request",
                )
                continue
            compatible = (
                finding_code is not None
                and citation.fault_code == finding_code  # type: ignore[union-attr]
                and citation.asset_type in (asset_type, "generic")  # type: ignore[union-attr]
                and (
                    not maintenance_required or citation.source_lane is RetrievalLane.MAINTENANCE  # type: ignore[union-attr]
                )
            )
            if not compatible:
                _add(
                    violations,
                    SafetyViolationCode.INCOMPATIBLE_CITATION,
                    f"{location}.citation_ids",
                    "Citation is not compatible with the referenced finding",
                )

    def _validate_generated_text(
        self,
        draft: CopilotDraft,
        prepared: PreparedCopilotRequest,
        violations: list[SafetyViolation],
    ) -> None:
        findings = {finding.finding_id: finding for finding in prepared.context.findings}
        allowed_summary_families = {
            _CODE_FAMILY[code]
            for code in (
                finding.code for finding in prepared.request.evidence_package.analysis.findings
            )
            if code in _CODE_FAMILY
        }
        text_fields: list[tuple[str, str, set[str]]] = [
            ("executive_summary", draft.executive_summary, allowed_summary_families),
        ]
        if draft.knowledge_gap_statement:
            text_fields.append(
                (
                    "knowledge_gap_statement",
                    draft.knowledge_gap_statement,
                    allowed_summary_families,
                )
            )
        for index, item in enumerate(draft.finding_explanations):
            finding = findings.get(item.finding_id)
            text_fields.append(
                (
                    f"finding_explanations.{index}.text",
                    item.text,
                    _allowed_families(finding.code if finding else None),
                )
            )
        for index, item in enumerate(draft.inspection_considerations):
            finding = findings.get(item.finding_id)
            location = f"inspection_considerations.{index}.text"
            text_fields.append(
                (location, item.text, _allowed_families(finding.code if finding else None))
            )
            if _INSPECTION_DIRECTIVE.search(item.text) and not _SAFE_INSPECTION_LANGUAGE.search(
                item.text
            ):
                _add(
                    violations,
                    SafetyViolationCode.HIGH_IMPACT_ACTION,
                    location,
                    "Inspection language must remain non-directive",
                )

        for location, text, allowed_families in text_fields:
            self._validate_text(location, text, allowed_families, violations)

    def _validate_text(
        self,
        location: str,
        text: str,
        allowed_families: set[str],
        violations: list[SafetyViolation],
    ) -> None:
        normalized = " ".join(text.lower().split())
        detected_families = {
            family
            for family, aliases in _FAULT_FAMILIES.items()
            if any(alias in normalized for alias in aliases)
        }
        if detected_families - allowed_families:
            _add(
                violations,
                SafetyViolationCode.UNSUPPORTED_FAULT_CLAIM,
                location,
                "Generated text introduces an unsupported fault",
            )
        checks = (
            (_PROBABILITY, SafetyViolationCode.UNSUPPORTED_PROBABILITY_CLAIM, "probability"),
            (_SEVERITY, SafetyViolationCode.UNSUPPORTED_SEVERITY_CLAIM, "severity"),
            (
                _HEALTH_RISK,
                SafetyViolationCode.UNSUPPORTED_HEALTH_OR_RISK_CLAIM,
                "health, risk, or remaining life",
            ),
            (_NUMERIC_TECHNICAL, SafetyViolationCode.UNSUPPORTED_NUMERIC_CLAIM, "numeric claim"),
            (_HIGH_IMPACT, SafetyViolationCode.HIGH_IMPACT_ACTION, "high-impact action"),
            (_MODEL_OVERCLAIM, SafetyViolationCode.MODEL_SCOPE_OVERCLAIM, "model-scope claim"),
            (_UNSAFE_MARKUP, SafetyViolationCode.UNSAFE_MARKUP, "unsafe markup"),
        )
        for pattern, code, description in checks:
            if pattern.search(text):
                _add(
                    violations,
                    code,
                    location,
                    f"Generated text contains an unsupported {description}",
                )


def _allowed_families(code: str | None) -> set[str]:
    if code is None or code not in _CODE_FAMILY:
        return set()
    return {_CODE_FAMILY[code]}


def _add(
    violations: list[SafetyViolation],
    code: SafetyViolationCode,
    location: str,
    message: str,
) -> None:
    if any(item.code is code and item.location == location for item in violations):
        return
    violations.append(SafetyViolation(code, location, message))


def violation_codes(result: ValidationResult) -> tuple[SafetyViolationCode, ...]:
    return tuple(dict.fromkeys(violation.code for violation in result.violations))


def has_violation(result: ValidationResult, codes: Iterable[SafetyViolationCode]) -> bool:
    expected = set(codes)
    return any(violation.code in expected for violation in result.violations)
