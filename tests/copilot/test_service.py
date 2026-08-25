from dataclasses import replace

import pytest

from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from modules.copilot.context import CopilotContextBuilder
from modules.copilot.contracts import (
    CopilotIntent,
    FallbackReason,
    GenerationStatus,
    MaintenanceCopilotRequest,
    RequestDisposition,
)
from modules.copilot.exceptions import CopilotInputError
from modules.copilot.report import verify_maintenance_report
from modules.copilot.service import MaintenanceCopilotService
from modules.copilot.validation import MaintenanceSafetyValidator
from shared.evidence.models import claim_support_for_analysis, create_evidence_package
from tests.copilot.support import (
    ChunkSpec,
    FakeMaintenanceGenerator,
    generated_result,
    make_bundle,
    make_prepared,
    make_valid_draft,
)


def _service(
    generator: FakeMaintenanceGenerator | None,
) -> MaintenanceCopilotService:
    return MaintenanceCopilotService(
        generator=generator,
        validator=MaintenanceSafetyValidator(),
    )


@pytest.mark.asyncio
async def test_confidence_is_a_successful_deterministic_report_without_provider() -> None:
    prepared = make_prepared(intent=CopilotIntent.EXPLAIN_CONFIDENCE)
    generator = FakeMaintenanceGenerator(generated_result(make_valid_draft()))

    report = await _service(generator).generate_report(prepared.request)

    assert generator.calls == []
    assert report.generation_status is GenerationStatus.DETERMINISTIC
    assert report.fallback_reason is None
    assert report.request_disposition is RequestDisposition.ANSWERED
    assert report.generation_provenance.provider == "none"
    assert report.generation_provenance.model is None
    assert "not a validated machine failure probability" in report.narrative.executive_summary
    assert report.analysis.findings[0].confidence == (
        prepared.request.evidence_package.analysis.findings[0].confidence
    )
    assert verify_maintenance_report(report, prepared)


@pytest.mark.asyncio
async def test_limitations_are_deterministic_without_fake_provider_identity() -> None:
    prepared = make_prepared(intent=CopilotIntent.EXPLAIN_LIMITATIONS)
    generator = FakeMaintenanceGenerator(generated_result(make_valid_draft()))

    report = await _service(generator).generate_report(prepared.request)

    assert generator.calls == []
    assert report.generation_status is GenerationStatus.DETERMINISTIC
    assert report.generation_provenance.provider == "none"
    assert report.generation_provenance.model is None
    assert "does not provide fault severity" in report.narrative.executive_summary
    assert report.analysis.claim_support == prepared.request.evidence_package.claim_support
    assert report.producing_models == prepared.request.evidence_package.models
    assert verify_maintenance_report(report, prepared)


@pytest.mark.asyncio
async def test_unsupported_high_impact_question_bypasses_graph_and_provider() -> None:
    prepared = make_prepared(question="Should I shut down this machine now?")
    generator = FakeMaintenanceGenerator(generated_result(make_valid_draft()))

    report = await _service(generator).generate_report(prepared.request)

    assert generator.calls == []
    assert report.generation_status is GenerationStatus.FALLBACK
    assert report.fallback_reason is FallbackReason.UNSUPPORTED_REQUEST
    assert report.request_disposition is RequestDisposition.NOT_SUPPORTED_BY_CURRENT_EVIDENCE
    assert "shut down this machine now" not in report.narrative.executive_summary.lower()
    assert report.citations == ()
    assert verify_maintenance_report(report, prepared)


@pytest.mark.asyncio
async def test_no_grounded_content_is_partial_fallback_without_provider() -> None:
    prepared = make_prepared(specs=())
    generator = FakeMaintenanceGenerator(generated_result(make_valid_draft()))

    report = await _service(generator).generate_report(prepared.request)

    assert generator.calls == []
    assert report.fallback_reason is FallbackReason.NO_GROUNDED_CONTENT
    assert report.request_disposition is RequestDisposition.PARTIALLY_ANSWERED
    assert report.citations == ()
    assert verify_maintenance_report(report, prepared)


@pytest.mark.asyncio
async def test_normal_inspection_and_insufficient_evidence_bypass_provider() -> None:
    normal = make_prepared("healthy", intent=CopilotIntent.INSPECTION_CONSIDERATIONS)
    insufficient = make_prepared(None, intent=CopilotIntent.EXPLAIN_FINDING)
    generator = FakeMaintenanceGenerator(generated_result(make_valid_draft()))
    service = _service(generator)

    normal_report = await service.generate_report(normal.request)
    insufficient_report = await service.generate_report(insufficient.request)

    assert generator.calls == []
    assert normal_report.analysis.condition is ConditionState.NORMAL
    assert normal_report.narrative.inspection_considerations == ()
    assert insufficient_report.analysis.status is AnalysisStatus.INSUFFICIENT_EVIDENCE
    assert insufficient_report.analysis.condition is ConditionState.INDETERMINATE
    assert insufficient_report.request_disposition is (
        RequestDisposition.NOT_SUPPORTED_BY_CURRENT_EVIDENCE
    )
    assert verify_maintenance_report(normal_report, normal)
    assert verify_maintenance_report(insufficient_report, insufficient)


@pytest.mark.asyncio
async def test_service_without_generator_supports_deterministic_and_unavailable_paths() -> None:
    service = _service(None)
    confidence = make_prepared(intent=CopilotIntent.EXPLAIN_CONFIDENCE)
    limitations = make_prepared(intent=CopilotIntent.EXPLAIN_LIMITATIONS)
    finding = make_prepared()

    confidence_report = await service.generate_report(confidence.request)
    limitations_report = await service.generate_report(limitations.request)
    finding_report = await service.generate_report(finding.request)

    assert service._workflow is None
    assert confidence_report.generation_status is GenerationStatus.DETERMINISTIC
    assert limitations_report.generation_status is GenerationStatus.DETERMINISTIC
    assert finding_report.fallback_reason is FallbackReason.GENERATION_UNAVAILABLE
    assert finding_report.request_disposition is RequestDisposition.PARTIALLY_ANSWERED
    assert verify_maintenance_report(confidence_report, confidence)
    assert verify_maintenance_report(limitations_report, limitations)
    assert verify_maintenance_report(finding_report, finding)


@pytest.mark.asyncio
async def test_indeterminate_condition_is_preserved_when_explicit_finding_is_explained() -> None:
    base = make_prepared()
    package = base.request.evidence_package
    analysis = replace(package.analysis, condition=ConditionState.INDETERMINATE)
    indeterminate_package = create_evidence_package(
        machine=package.machine,
        analysis=analysis,
        sources=package.sources,
        models=package.models,
        claim_support=claim_support_for_analysis(analysis),
    )
    request = MaintenanceCopilotRequest(
        evidence_package=indeterminate_package,
        retrieval_bundle=make_bundle(
            indeterminate_package,
            (ChunkSpec("bearing_fault"),),
        ),
        intent=CopilotIntent.EXPLAIN_FINDING,
    )
    prepared = CopilotContextBuilder().build(request)
    generator = FakeMaintenanceGenerator(generated_result(make_valid_draft()))

    report = await _service(generator).generate_report(request)

    assert len(generator.calls) == 1
    assert report.analysis.condition is ConditionState.INDETERMINATE
    assert report.request_disposition is RequestDisposition.ANSWERED
    assert verify_maintenance_report(report, prepared)


@pytest.mark.parametrize("kind", ["evidence", "retrieval", "mismatch"])
@pytest.mark.asyncio
async def test_tampered_or_mismatched_input_is_a_hard_failure_before_provider(kind: str) -> None:
    prepared = make_prepared()
    if kind == "evidence":
        request = replace(
            prepared.request,
            evidence_package=replace(
                prepared.request.evidence_package,
                machine=replace(prepared.request.evidence_package.machine, name="Tampered"),
            ),
        )
    elif kind == "retrieval":
        request = replace(
            prepared.request,
            retrieval_bundle=replace(
                prepared.request.retrieval_bundle,
                chunks=(
                    replace(
                        prepared.request.retrieval_bundle.chunks[0],
                        text="Tampered source content",
                    ),
                ),
            ),
        )
    else:
        request = replace(
            prepared.request,
            retrieval_bundle=make_prepared("misalignment").request.retrieval_bundle,
        )
    generator = FakeMaintenanceGenerator(generated_result(make_valid_draft()))

    with pytest.raises(CopilotInputError):
        await _service(generator).generate_report(request)

    assert generator.calls == []
