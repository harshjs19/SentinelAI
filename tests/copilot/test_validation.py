import pytest

from domain.enums.modality import Modality
from modules.copilot.contracts import (
    CopilotDraft,
    DraftFindingExplanation,
    DraftInspectionConsideration,
    SafetyViolationCode,
)
from modules.copilot.validation import MaintenanceSafetyValidator, violation_codes
from modules.retriever.models import RetrievalLane
from tests.copilot.support import ChunkSpec, make_prepared


def _explanation(
    text: str,
    *,
    finding_id: str = "F1",
    citation_ids: tuple[str, ...] = ("K1",),
) -> CopilotDraft:
    return CopilotDraft(
        executive_summary="The analysis contains a source finding.",
        finding_explanations=(
            DraftFindingExplanation(
                finding_id=finding_id,
                text=text,
                citation_ids=citation_ids,
            ),
        ),
    )


def _inspection(
    text: str,
    *,
    citation_ids: tuple[str, ...] = ("K1",),
) -> CopilotDraft:
    return CopilotDraft(
        executive_summary="The analysis contains a source finding.",
        inspection_considerations=(
            DraftInspectionConsideration(
                finding_id="F1",
                text=text,
                citation_ids=citation_ids,
            ),
        ),
    )


def _codes(draft: CopilotDraft | object, prepared=None) -> tuple[SafetyViolationCode, ...]:
    result = MaintenanceSafetyValidator().validate(draft, prepared or make_prepared())
    return violation_codes(result)


def test_valid_bearing_explanation_and_inspection_are_accepted() -> None:
    prepared = make_prepared()
    draft = CopilotDraft(
        executive_summary="The analysis reported a bearing fault.",
        finding_explanations=(
            DraftFindingExplanation(
                finding_id="F1",
                text=(
                    "The retrieved reference describes bearing-related condition indicators "
                    "relevant to the reported finding."
                ),
                citation_ids=("K1",),
            ),
        ),
        inspection_considerations=(
            DraftInspectionConsideration(
                finding_id="F1",
                text=(
                    "Inspection could consider the bearing-related areas described by the "
                    "cited reference."
                ),
                citation_ids=("K1",),
            ),
        ),
    )

    result = MaintenanceSafetyValidator().validate(draft, prepared)

    assert result.valid is True
    assert result.violations == ()


@pytest.mark.parametrize(
    ("modality", "code"),
    [
        (Modality.VISION, "visual_anomaly"),
        (Modality.AUDIO, "acoustic_anomaly"),
    ],
)
def test_anomaly_cannot_be_converted_to_bearing_fault(
    modality: Modality,
    code: str,
) -> None:
    prepared = make_prepared(code, modality=modality)
    draft = _explanation("This pattern suggests bearing fault.")

    assert SafetyViolationCode.UNSUPPORTED_FAULT_CLAIM in _codes(draft, prepared)


def test_cross_fault_text_and_citation_are_both_rejected() -> None:
    prepared = make_prepared(
        specs=(
            ChunkSpec("bearing_fault"),
            ChunkSpec("gear_wear_75"),
        )
    )
    draft = _explanation("This indicates gear wear.", citation_ids=("K2",))
    codes = _codes(draft, prepared)

    assert SafetyViolationCode.UNSUPPORTED_FAULT_CLAIM in codes
    assert SafetyViolationCode.INCOMPATIBLE_CITATION in codes


@pytest.mark.parametrize(
    ("text", "required_codes"),
    [
        (
            "There is a 93% chance the machine will fail.",
            {
                SafetyViolationCode.UNSUPPORTED_PROBABILITY_CLAIM,
                SafetyViolationCode.UNSUPPORTED_NUMERIC_CLAIM,
            },
        ),
        (
            "This is a severe fault.",
            {SafetyViolationCode.UNSUPPORTED_SEVERITY_CLAIM},
        ),
        (
            "Operational risk is high.",
            {SafetyViolationCode.UNSUPPORTED_HEALTH_OR_RISK_CLAIM},
        ),
        (
            "The component has 3 hours remaining.",
            {
                SafetyViolationCode.UNSUPPORTED_HEALTH_OR_RISK_CLAIM,
                SafetyViolationCode.UNSUPPORTED_NUMERIC_CLAIM,
            },
        ),
        (
            "Check for 10 mm of movement.",
            {SafetyViolationCode.UNSUPPORTED_NUMERIC_CLAIM},
        ),
        (
            "Operate below 80 C.",
            {SafetyViolationCode.UNSUPPORTED_NUMERIC_CLAIM},
        ),
    ],
)
def test_unsupported_quantitative_and_claim_categories_fail(
    text: str,
    required_codes: set[SafetyViolationCode],
) -> None:
    assert required_codes <= set(_codes(_explanation(text)))


@pytest.mark.parametrize(
    "text",
    [
        "Shut down the machine immediately.",
        "Replace the bearing.",
        "You must inspect the bearing.",
        "Inspect immediately.",
        "Continue operating the machine.",
        "Return to service after inspection.",
    ],
)
def test_high_impact_or_directive_actions_fail(text: str) -> None:
    assert SafetyViolationCode.HIGH_IMPACT_ACTION in _codes(_inspection(text))


@pytest.mark.parametrize(
    "text",
    [
        "[click](https://evil.example)",
        "<script>alert(1)</script>",
        "```bash echo unsafe```",
        "See https://evil.example",
    ],
)
def test_generated_markup_and_urls_fail(text: str) -> None:
    assert SafetyViolationCode.UNSAFE_MARKUP in _codes(_explanation(text))


@pytest.mark.parametrize(
    "text",
    [
        "This model is universally validated for industrial machinery.",
        "This model guarantees detection.",
        "The model always detects this condition.",
    ],
)
def test_model_scope_overclaim_fails(text: str) -> None:
    assert SafetyViolationCode.MODEL_SCOPE_OVERCLAIM in _codes(_explanation(text))


def test_unknown_missing_duplicate_and_wrong_lane_citations_fail() -> None:
    prepared = make_prepared()
    assert SafetyViolationCode.UNKNOWN_CITATION in _codes(
        _explanation("Source-backed bearing-related context.", citation_ids=("K99",)),
        prepared,
    )

    missing_item = DraftFindingExplanation.model_construct(
        finding_id="F1",
        text="Source-backed bearing-related context.",
        citation_ids=(),
    )
    missing_draft = CopilotDraft(
        executive_summary="The analysis contains a source finding.",
        finding_explanations=(missing_item,),
    )
    assert SafetyViolationCode.MISSING_CITATION in _codes(missing_draft, prepared)

    duplicate_item = DraftFindingExplanation.model_construct(
        finding_id="F1",
        text="Source-backed bearing-related context.",
        citation_ids=("K1", "K1"),
    )
    duplicate_draft = CopilotDraft(
        executive_summary="The analysis contains a source finding.",
        finding_explanations=(duplicate_item,),
    )
    assert SafetyViolationCode.INCOMPATIBLE_CITATION in _codes(duplicate_draft, prepared)

    interpretation_prepared = make_prepared(
        specs=(ChunkSpec("bearing_fault", lane=RetrievalLane.INTERPRETATION),)
    )
    assert SafetyViolationCode.INCOMPATIBLE_CITATION in _codes(
        _inspection("Inspection could consider the bearing-related areas in the reference."),
        interpretation_prepared,
    )


def test_generic_asset_is_compatible_only_when_fault_code_matches() -> None:
    generic = make_prepared(specs=(ChunkSpec("bearing_fault", asset_type="generic"),))
    valid = _explanation("The reference provides bearing-related condition context.")
    assert MaintenanceSafetyValidator().validate(valid, generic).valid

    wrong_fault = make_prepared(specs=(ChunkSpec("gear_wear_75", asset_type="generic"),))
    invalid = _explanation("The reference provides bearing-related condition context.")
    assert SafetyViolationCode.INCOMPATIBLE_CITATION in _codes(invalid, wrong_fault)


def test_invalid_finding_reference_and_duplicate_items_fail() -> None:
    unknown = _explanation(
        "The reference provides bearing-related condition context.",
        finding_id="F99",
    )
    assert SafetyViolationCode.INVALID_FINDING_REFERENCE in _codes(unknown)

    item = DraftFindingExplanation(
        finding_id="F1",
        text="The reference provides bearing-related condition context.",
        citation_ids=("K1",),
    )
    duplicate = CopilotDraft(
        executive_summary="The analysis contains a source finding.",
        finding_explanations=(item, item),
    )
    assert SafetyViolationCode.INVALID_FINDING_REFERENCE in _codes(duplicate)


def test_normal_summary_cannot_invent_a_physical_fault() -> None:
    prepared = make_prepared("healthy")
    draft = CopilotDraft(executive_summary="The analysis suggests a bearing fault.")

    assert SafetyViolationCode.UNSUPPORTED_FAULT_CLAIM in _codes(draft, prepared)


def test_malformed_draft_maps_to_schema_invalid_without_content_leak() -> None:
    result = MaintenanceSafetyValidator().validate(
        {"executive_summary": "unsafe private generated text", "unexpected": True},
        make_prepared(),
    )

    assert violation_codes(result) == (SafetyViolationCode.SCHEMA_INVALID,)
    assert "unsafe private" not in result.violations[0].message


def test_constructed_over_limit_draft_fails_closed() -> None:
    draft = CopilotDraft.model_construct(
        executive_summary="x" * 701,
        finding_explanations=(),
        inspection_considerations=(),
        knowledge_gap_statement=None,
    )

    assert SafetyViolationCode.CONTENT_LIMIT_EXCEEDED in _codes(draft)
