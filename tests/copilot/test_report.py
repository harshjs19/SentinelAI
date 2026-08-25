import hashlib
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from ai_core.model_capabilities import ModelLifecycleStatus
from domain.enums.condition_state import ConditionState
from domain.enums.modality import Modality
from domain.enums.risk_level import RiskLevel
from modules.copilot.context import CopilotContextBuilder
from modules.copilot.contracts import (
    CopilotDraft,
    DraftFindingExplanation,
    DraftInspectionConsideration,
    FallbackReason,
    GenerationStatus,
    MaintenanceCopilotRequest,
    RequestDisposition,
    SafetyViolation,
    SafetyViolationCode,
    ValidationResult,
)
from modules.copilot.report import (
    FALLBACK_EXECUTIVE_SUMMARY,
    FALLBACK_KNOWLEDGE_GAP,
    MAINTENANCE_REPORT_DISCLAIMER,
    assemble_fallback_report,
    assemble_maintenance_report,
    fake_generation_provenance,
    maintenance_report_core_payload,
    maintenance_report_payload,
    verify_maintenance_report,
    verify_report_digest,
)
from modules.copilot.validation import MaintenanceSafetyValidator
from shared.evidence.canonical import canonical_json_bytes
from shared.evidence.models import claim_support_for_analysis, create_evidence_package
from tests.copilot.support import ChunkSpec, make_bundle, make_prepared

REPORT_ID = UUID("00000000-0000-0000-0000-00000000c001")
GENERATED_AT = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


def _draft(citation_id: str = "K1") -> CopilotDraft:
    return CopilotDraft(
        executive_summary="The analysis reported a bearing fault.",
        finding_explanations=(
            DraftFindingExplanation(
                finding_id="F1",
                text="The cited source provides bearing-related condition context.",
                citation_ids=(citation_id,),
            ),
        ),
        inspection_considerations=(
            DraftInspectionConsideration(
                finding_id="F1",
                text="Inspection could consider bearing-related areas in the cited source.",
                citation_ids=(citation_id,),
            ),
        ),
    )


def _report(prepared=None, draft=None):
    prepared = prepared or make_prepared()
    draft = draft or _draft()
    validation = MaintenanceSafetyValidator().validate(draft, prepared)
    assert validation.valid
    return assemble_maintenance_report(
        prepared,
        draft,
        fake_generation_provenance(),
        validation,
        report_id=REPORT_ID,
        generated_at=GENERATED_AT,
    )


def _digest_for_core(report) -> str:
    return hashlib.sha256(canonical_json_bytes(maintenance_report_core_payload(report))).hexdigest()


def test_report_copies_authoritative_evidence_and_only_used_citations() -> None:
    prepared = make_prepared(specs=(ChunkSpec("bearing_fault"), ChunkSpec("bearing_fault")))
    report = _report(prepared)
    package = prepared.request.evidence_package

    assert report.generation_status is GenerationStatus.GENERATED
    assert report.fallback_reason is None
    assert report.machine == package.machine
    assert report.analysis.condition is package.analysis.condition
    assert report.analysis.status is package.analysis.status
    assert report.analysis.health_score == package.analysis.health_score
    assert report.analysis.risk_level is package.analysis.risk_level
    assert report.analysis.claim_support == package.claim_support
    assert report.analysis.findings[0].confidence == package.analysis.findings[0].confidence
    assert report.producing_models == package.models
    assert report.producing_models[0].confidence_semantics == ("raw_selected_class_predict_proba")
    assert [citation.citation_id for citation in report.citations] == ["K1"]
    assert report.citations[0].source_uri.startswith("https://")
    assert report.disclaimer == MAINTENANCE_REPORT_DISCLAIMER
    assert verify_report_digest(report)
    assert verify_maintenance_report(report, prepared)


def test_experimental_model_status_is_preserved_without_suppressing_cited_context() -> None:
    prepared = make_prepared(
        "acoustic_anomaly",
        modality=Modality.AUDIO,
    )
    draft = CopilotDraft(
        executive_summary="The analysis reported an acoustic anomaly.",
        finding_explanations=(
            DraftFindingExplanation(
                finding_id="F1",
                text="The cited source describes the reported acoustic anomaly.",
                citation_ids=("K1",),
            ),
        ),
    )
    report = _report(prepared, draft)

    assert report.producing_models[0].status is ModelLifecycleStatus.EXPERIMENTAL
    assert report.citations


def test_report_digest_is_repeatable_for_injected_identity_and_time() -> None:
    first = _report()
    second = _report()

    assert first == second
    assert first.report_digest_sha256 == second.report_digest_sha256
    assert maintenance_report_payload(first) == maintenance_report_payload(second)


def test_report_digest_changes_with_narrative_citation_evidence_or_model_context() -> None:
    prepared = make_prepared(specs=(ChunkSpec("bearing_fault"), ChunkSpec("bearing_fault")))
    original = _report(prepared)
    changed_narrative = _report(
        prepared,
        CopilotDraft(
            executive_summary="The analysis includes a bearing fault finding.",
            finding_explanations=original.narrative.finding_explanations,
            inspection_considerations=original.narrative.inspection_considerations,
        ),
    )
    changed_citation = _report(prepared, _draft("K2"))
    changed_evidence = replace(
        original,
        evidence_reference=replace(original.evidence_reference, package_id="evp1_changed"),
    )
    changed_model = replace(
        original,
        producing_models=(replace(original.producing_models[0], validated_scope="changed scope"),),
    )

    assert changed_narrative.report_digest_sha256 != original.report_digest_sha256
    assert changed_citation.report_digest_sha256 != original.report_digest_sha256
    assert _digest_for_core(changed_evidence) != original.report_digest_sha256
    assert _digest_for_core(changed_model) != original.report_digest_sha256


def test_tampering_while_retaining_old_digest_fails_verification() -> None:
    report = _report()
    tampered = replace(
        report,
        analysis=replace(report.analysis, condition=ConditionState.NORMAL),
    )

    assert not verify_report_digest(tampered)
    assert not verify_maintenance_report(tampered, make_prepared())


@pytest.mark.parametrize("reason", list(FallbackReason))
def test_every_fallback_reason_preserves_evidence_and_has_no_citations(
    reason: FallbackReason,
) -> None:
    prepared = make_prepared()
    report = assemble_fallback_report(
        prepared,
        reason,
        report_id=REPORT_ID,
        generated_at=GENERATED_AT,
    )
    package = prepared.request.evidence_package

    assert report.generation_status is GenerationStatus.FALLBACK
    assert report.fallback_reason is reason
    assert report.machine == package.machine
    assert report.analysis.condition is package.analysis.condition
    assert report.analysis.health_score == package.analysis.health_score
    assert report.analysis.risk_level is package.analysis.risk_level
    assert report.analysis.claim_support == package.claim_support
    assert report.producing_models == package.models
    assert report.narrative.executive_summary == FALLBACK_EXECUTIVE_SUMMARY
    assert report.narrative.finding_explanations == ()
    assert report.narrative.inspection_considerations == ()
    assert report.narrative.knowledge_gap_statement == FALLBACK_KNOWLEDGE_GAP
    assert report.citations == ()
    assert verify_report_digest(report)
    assert verify_maintenance_report(report, prepared)


def test_fallback_preserves_available_health_and_risk_exactly() -> None:
    base = make_prepared()
    original = base.request.evidence_package
    analysis = replace(original.analysis, health_score=42.0, risk_level=RiskLevel.HIGH)
    package = create_evidence_package(
        machine=original.machine,
        analysis=analysis,
        sources=original.sources,
        models=original.models,
        claim_support=claim_support_for_analysis(analysis),
    )
    prepared = CopilotContextBuilder().build(
        MaintenanceCopilotRequest(
            package,
            make_bundle(package, (ChunkSpec("bearing_fault"),)),
            base.request.intent,
        )
    )
    report = assemble_fallback_report(
        prepared,
        FallbackReason.GENERATION_UNAVAILABLE,
        report_id=REPORT_ID,
        generated_at=GENERATED_AT,
    )

    assert report.analysis.health_score == 42.0
    assert report.analysis.risk_level is RiskLevel.HIGH
    assert report.analysis.claim_support.health_score_available is True
    assert report.analysis.claim_support.operational_risk_available is True
    assert verify_maintenance_report(report, prepared)


def test_validation_failure_fallback_records_codes_but_not_rejected_text() -> None:
    prepared = make_prepared()
    invalid = ValidationResult(
        valid=False,
        violations=(
            SafetyViolation(
                SafetyViolationCode.HIGH_IMPACT_ACTION,
                "inspection_considerations.0.text",
                "Generated text contains an unsupported high-impact action",
            ),
        ),
    )
    report = assemble_fallback_report(
        prepared,
        FallbackReason.VALIDATION_FAILED,
        validation=invalid,
        generation_provenance=fake_generation_provenance(repair_attempted=True),
        report_id=REPORT_ID,
        generated_at=GENERATED_AT,
    )

    payload = canonical_json_bytes(maintenance_report_payload(report)).decode()
    assert report.safety_validation.valid is False
    assert report.safety_validation.repair_attempted is True
    assert "high_impact_action" in payload
    assert "Shut down" not in payload
    assert report.citations == ()


def test_unsupported_and_no_grounded_fallback_dispositions_are_not_supported() -> None:
    prepared = make_prepared()
    for reason in (FallbackReason.UNSUPPORTED_REQUEST, FallbackReason.NO_GROUNDED_CONTENT):
        report = assemble_fallback_report(
            prepared,
            reason,
            report_id=REPORT_ID,
            generated_at=GENERATED_AT,
        )
        assert report.request_disposition is RequestDisposition.NOT_SUPPORTED_BY_CURRENT_EVIDENCE


def test_generated_report_rejects_an_invalid_validation_result() -> None:
    invalid = ValidationResult(
        valid=False,
        violations=(
            SafetyViolation(
                SafetyViolationCode.SCHEMA_INVALID,
                "draft",
                "Draft does not match the Copilot schema",
            ),
        ),
    )

    with pytest.raises(ValueError, match="invalid Copilot draft"):
        assemble_maintenance_report(
            make_prepared(),
            _draft(),
            fake_generation_provenance(),
            invalid,
        )


def test_final_invariant_verifier_detects_citation_and_model_tampering() -> None:
    prepared = make_prepared()
    report = _report(prepared)
    wrong_citation = replace(
        report.citations[0],
        source_uri="https://example.invalid/changed",
    )
    citation_tampered = replace(
        report,
        citations=(wrong_citation,),
        report_digest_sha256="0" * 64,
    )
    citation_tampered = replace(
        citation_tampered,
        report_digest_sha256=_digest_for_core(citation_tampered),
    )
    model_tampered = replace(
        report,
        producing_models=(replace(report.producing_models[0], model_id="other-model"),),
        report_digest_sha256="0" * 64,
    )
    model_tampered = replace(
        model_tampered,
        report_digest_sha256=_digest_for_core(model_tampered),
    )

    assert verify_report_digest(citation_tampered)
    assert verify_report_digest(model_tampered)
    assert not verify_maintenance_report(citation_tampered, prepared)
    assert not verify_maintenance_report(model_tampered, prepared)


def test_report_and_nested_contracts_are_immutable() -> None:
    report = _report()

    with pytest.raises(FrozenInstanceError):
        report.disclaimer = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        report.analysis.condition = ConditionState.NORMAL  # type: ignore[misc]
