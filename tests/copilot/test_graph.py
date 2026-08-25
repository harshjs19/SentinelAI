import pytest

from domain.enums.modality import Modality
from modules.copilot.contracts import (
    CopilotDraft,
    DraftInspectionConsideration,
    FallbackReason,
    GenerationStatus,
    RequestDisposition,
    SafetyViolationCode,
)
from modules.copilot.generator import GenerationFailureCode, MaintenanceGenerationError
from modules.copilot.graph import (
    COPILOT_GRAPH_RECURSION_LIMIT,
    COPILOT_WORKFLOW_VERSION,
    CopilotGraphState,
    CopilotWorkflowError,
    MaintenanceCopilotWorkflow,
    fallback_reason_for_generation_failure,
    route_after_validation,
)
from modules.copilot.report import maintenance_report_payload, verify_maintenance_report
from modules.copilot.validation import MaintenanceSafetyValidator
from shared.evidence.canonical import canonical_json_bytes
from tests.copilot.support import (
    ChunkSpec,
    FakeMaintenanceGenerator,
    generated_result,
    make_prepared,
    make_valid_draft,
)


def _high_impact_draft() -> CopilotDraft:
    return CopilotDraft(
        executive_summary="The analysis reported a bearing fault.",
        inspection_considerations=(
            DraftInspectionConsideration(
                finding_id="F1",
                text="Shut down the machine immediately.",
                citation_ids=("K1",),
            ),
        ),
    )


def _workflow(generator: FakeMaintenanceGenerator) -> MaintenanceCopilotWorkflow:
    return MaintenanceCopilotWorkflow(
        generator=generator,
        validator=MaintenanceSafetyValidator(),
    )


def test_graph_compiles_only_the_five_bounded_nodes_without_checkpointing() -> None:
    workflow = _workflow(FakeMaintenanceGenerator(generated_result(make_valid_draft())))

    assert workflow.compiled_node_names() == {
        "__start__",
        "generate_draft",
        "validate_draft",
        "repair_draft",
        "finalize_report",
        "fallback_report",
        "__end__",
    }
    assert workflow._graph.checkpointer is None
    assert COPILOT_GRAPH_RECURSION_LIMIT == 8
    assert COPILOT_WORKFLOW_VERSION == "maintenance_graph_v1"


def test_graph_state_contains_only_request_scoped_report_workflow_fields() -> None:
    assert set(CopilotGraphState.__annotations__) == {
        "prepared",
        "draft",
        "generated_result",
        "validation_result",
        "repair_count",
        "fallback_reason",
        "generation_provenance",
        "final_report",
    }
    forbidden = {
        "api_key",
        "openai_client",
        "database_session",
        "chroma_client",
        "embedding_model",
        "predictor",
        "event_bus",
        "filesystem_path",
        "environment",
        "raw_media",
        "raw_sensor_data",
    }
    assert forbidden.isdisjoint(CopilotGraphState.__annotations__)


def test_route_rejects_an_out_of_bounds_repair_count_before_another_call() -> None:
    prepared = make_prepared()
    state = CopilotGraphState(
        prepared=prepared,
        draft=_high_impact_draft(),
        generated_result=generated_result(_high_impact_draft()),
        validation_result=MaintenanceSafetyValidator().validate(_high_impact_draft(), prepared),
        repair_count=2,
        fallback_reason=None,
        generation_provenance=None,
        final_report=None,
    )

    with pytest.raises(CopilotWorkflowError, match="repair count"):
        route_after_validation(state)


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        (GenerationFailureCode.CONFIGURATION, FallbackReason.GENERATION_UNAVAILABLE),
        (GenerationFailureCode.AUTHENTICATION, FallbackReason.GENERATION_UNAVAILABLE),
        (GenerationFailureCode.TRANSIENT, FallbackReason.GENERATION_UNAVAILABLE),
        (GenerationFailureCode.REFUSED, FallbackReason.GENERATION_FAILED),
        (GenerationFailureCode.INCOMPLETE, FallbackReason.GENERATION_FAILED),
        (GenerationFailureCode.MALFORMED_OUTPUT, FallbackReason.GENERATION_FAILED),
        (GenerationFailureCode.PROVIDER_ERROR, FallbackReason.GENERATION_FAILED),
    ],
)
def test_provider_failure_mapping_is_small_and_deterministic(
    code: GenerationFailureCode,
    reason: FallbackReason,
) -> None:
    assert fallback_reason_for_generation_failure(code) is reason


@pytest.mark.asyncio
async def test_valid_initial_draft_finalizes_with_one_logical_call() -> None:
    prepared = make_prepared()
    generator = FakeMaintenanceGenerator(generated_result(make_valid_draft()))

    report = await _workflow(generator).run(prepared)

    assert len(generator.calls) == 1
    assert generator.calls[0] == (prepared.context, None)
    assert report.generation_status is GenerationStatus.GENERATED
    assert report.fallback_reason is None
    assert report.narrative.finding_explanations == make_valid_draft().finding_explanations
    assert [citation.citation_id for citation in report.citations] == ["K1"]
    assert report.analysis.condition is prepared.request.evidence_package.analysis.condition
    assert report.safety_validation.valid is True
    assert report.safety_validation.repair_attempted is False
    assert verify_maintenance_report(report, prepared)


@pytest.mark.asyncio
async def test_valid_draft_with_explicit_knowledge_gap_is_partially_answered() -> None:
    prepared = make_prepared()
    draft = CopilotDraft(
        executive_summary="The analysis reported a bearing fault.",
        finding_explanations=make_valid_draft().finding_explanations,
        knowledge_gap_statement="The supplied sources do not cover further interpretation.",
    )
    generator = FakeMaintenanceGenerator(generated_result(draft))

    report = await _workflow(generator).run(prepared)

    assert report.request_disposition is RequestDisposition.PARTIALLY_ANSWERED
    assert len(generator.calls) == 1
    assert verify_maintenance_report(report, prepared)


@pytest.mark.asyncio
async def test_final_invariant_failure_is_not_hidden_as_provider_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = make_prepared()
    generator = FakeMaintenanceGenerator(generated_result(make_valid_draft()))
    monkeypatch.setattr("modules.copilot.graph.verify_maintenance_report", lambda *_: False)

    with pytest.raises(CopilotWorkflowError, match="invariant verification failed"):
        await _workflow(generator).run(prepared)


@pytest.mark.asyncio
async def test_invalid_initial_valid_repair_uses_exactly_two_calls() -> None:
    prepared = make_prepared()
    safe = make_valid_draft(
        finding_text="The cited source provides bearing-related inspection context."
    )
    generator = FakeMaintenanceGenerator(
        generated_result(_high_impact_draft()),
        generated_result(safe, repair_attempted=True),
    )

    report = await _workflow(generator).run(prepared)

    assert len(generator.calls) == 2
    initial_context, initial_repair = generator.calls[0]
    repair_context, repair_instruction = generator.calls[1]
    assert initial_context is repair_context is prepared.context
    assert initial_repair is None
    assert repair_instruction is not None
    assert repair_instruction.previous_draft == _high_impact_draft()
    assert SafetyViolationCode.HIGH_IMPACT_ACTION in repair_instruction.violation_codes
    assert report.generation_status is GenerationStatus.GENERATED
    assert report.safety_validation.repair_attempted is True
    payload = canonical_json_bytes(maintenance_report_payload(report)).decode()
    assert "Shut down" not in payload
    assert safe.finding_explanations[0].text in payload
    assert verify_maintenance_report(report, prepared)


@pytest.mark.asyncio
async def test_invalid_repair_falls_back_without_a_third_call_or_rejected_prose() -> None:
    prepared = make_prepared(specs=tuple(ChunkSpec("bearing_fault") for _ in range(8)))
    generator = FakeMaintenanceGenerator(
        generated_result(_high_impact_draft()),
        generated_result(_high_impact_draft(), repair_attempted=True),
        generated_result(make_valid_draft(), repair_attempted=True),
    )

    report = await _workflow(generator).run(prepared)

    assert len(generator.calls) == 2
    assert report.generation_status is GenerationStatus.FALLBACK
    assert report.fallback_reason is FallbackReason.VALIDATION_FAILED
    assert report.citations == ()
    assert report.narrative.finding_explanations == ()
    assert report.narrative.inspection_considerations == ()
    payload = canonical_json_bytes(maintenance_report_payload(report)).decode()
    assert "Shut down" not in payload
    assert report.analysis.findings[0].code == "bearing_fault"
    assert report.producing_models == prepared.request.evidence_package.models
    assert verify_maintenance_report(report, prepared)


@pytest.mark.asyncio
async def test_initial_provider_failure_falls_back_without_repair() -> None:
    prepared = make_prepared()
    generator = FakeMaintenanceGenerator(
        MaintenanceGenerationError(GenerationFailureCode.TRANSIENT)
    )

    report = await _workflow(generator).run(prepared)

    assert len(generator.calls) == 1
    assert report.fallback_reason is FallbackReason.GENERATION_UNAVAILABLE
    assert report.citations == ()
    assert report.analysis.condition is prepared.request.evidence_package.analysis.condition
    assert verify_maintenance_report(report, prepared)


@pytest.mark.asyncio
async def test_repair_provider_failure_falls_back_without_third_call() -> None:
    prepared = make_prepared()
    generator = FakeMaintenanceGenerator(
        generated_result(_high_impact_draft()),
        MaintenanceGenerationError(GenerationFailureCode.REFUSED),
        generated_result(make_valid_draft(), repair_attempted=True),
    )

    report = await _workflow(generator).run(prepared)

    assert len(generator.calls) == 2
    assert report.fallback_reason is FallbackReason.GENERATION_FAILED
    assert report.safety_validation.repair_attempted is True
    assert "Shut down" not in canonical_json_bytes(maintenance_report_payload(report)).decode()
    assert verify_maintenance_report(report, prepared)


@pytest.mark.asyncio
async def test_hallucinated_fault_is_repaired_without_changing_visual_evidence() -> None:
    prepared = make_prepared("visual_anomaly", modality=Modality.VISION)
    hallucinated = make_valid_draft(
        summary="The analysis reported a visual anomaly.",
        finding_text="This indicates a bearing fault.",
    )
    repaired = make_valid_draft(
        summary="The analysis reported a visual anomaly.",
        finding_text="The cited source describes the reported visual anomaly.",
    )
    generator = FakeMaintenanceGenerator(
        generated_result(hallucinated),
        generated_result(repaired, repair_attempted=True),
    )

    report = await _workflow(generator).run(prepared)

    repair = generator.calls[1][1]
    assert repair is not None
    assert SafetyViolationCode.UNSUPPORTED_FAULT_CLAIM in repair.violation_codes
    assert report.analysis.findings[0].code == "visual_anomaly"
    assert "bearing" not in report.narrative.finding_explanations[0].text.lower()
    assert verify_maintenance_report(report, prepared)


@pytest.mark.asyncio
async def test_failure_probability_is_repaired_while_upstream_confidence_is_preserved() -> None:
    prepared = make_prepared()
    probability = make_valid_draft(summary="There is a 93% chance of failure.")
    repaired = make_valid_draft()
    generator = FakeMaintenanceGenerator(
        generated_result(probability),
        generated_result(repaired, repair_attempted=True),
    )

    report = await _workflow(generator).run(prepared)

    repair = generator.calls[1][1]
    assert repair is not None
    assert SafetyViolationCode.UNSUPPORTED_PROBABILITY_CLAIM in repair.violation_codes
    payload = canonical_json_bytes(maintenance_report_payload(report)).decode()
    assert "93%" not in payload
    assert report.analysis.findings[0].confidence == (
        prepared.request.evidence_package.analysis.findings[0].confidence
    )
    assert verify_maintenance_report(report, prepared)


@pytest.mark.asyncio
async def test_unknown_citation_is_repaired_from_original_retrieval_mapping() -> None:
    prepared = make_prepared()
    unknown = make_valid_draft(citation_id="K99")
    repaired = make_valid_draft(citation_id="K1")
    generator = FakeMaintenanceGenerator(
        generated_result(unknown),
        generated_result(repaired, repair_attempted=True),
    )

    report = await _workflow(generator).run(prepared)

    repair = generator.calls[1][1]
    assert repair is not None
    assert SafetyViolationCode.UNKNOWN_CITATION in repair.violation_codes
    assert report.citations == (prepared.assigned_citations[0].citation,)
    assert verify_maintenance_report(report, prepared)
