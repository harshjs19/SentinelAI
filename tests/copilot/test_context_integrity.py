from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from backend.app.services.evidence_package_service import EvidencePackageService
from domain.entities.analysis import Analysis
from domain.entities.finding import Finding
from domain.entities.machine import Machine
from domain.entities.prediction import Prediction
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from domain.enums.modality import Modality
from modules.copilot.context import CopilotContextBuilder, generation_context_payload
from modules.copilot.contracts import CopilotIntent, MaintenanceCopilotRequest
from modules.copilot.exceptions import CopilotInputError, CopilotInputErrorCode
from modules.retriever.models import RetrievalLane, create_retrieval_bundle
from shared.evidence.canonical import canonical_json_bytes
from shared.evidence.provenance import file_source_provenance, structured_source_provenance
from tests.copilot.support import EMBEDDING_IDENTITY, ChunkSpec, make_bundle, make_prepared
from tests.retriever.support import make_evidence_package


def test_context_assigns_deterministic_request_local_citation_ids() -> None:
    prepared = make_prepared(
        specs=(
            ChunkSpec("bearing_fault", text="First source"),
            ChunkSpec("bearing_fault", text="Second source"),
        )
    )

    assert [item.citation.citation_id for item in prepared.assigned_citations] == ["K1", "K2"]
    assert [item.provider_context.citation_id for item in prepared.assigned_citations] == [
        "K1",
        "K2",
    ]
    assert prepared.assigned_citations[0].citation.source_uri.startswith("https://")
    assert not hasattr(prepared.assigned_citations[0].provider_context, "source_uri")


def test_provider_context_is_minimized_and_contains_no_private_provenance() -> None:
    prepared = make_prepared(
        specs=(
            ChunkSpec(
                "bearing_fault",
                source_uri="file:///C:/private/chroma/source.html",
                source_digest_sha256="a" * 64,
                text="Approved bearing condition reference.",
            ),
        )
    )
    serialized = canonical_json_bytes(generation_context_payload(prepared.context)).decode()

    forbidden = (
        str(prepared.request.evidence_package.machine.machine_id),
        prepared.request.evidence_package.machine.name,
        prepared.request.evidence_package.package_digest_sha256,
        prepared.request.retrieval_bundle.retrieval_bundle_digest_sha256,
        "file:///C:/private/chroma/source.html",
        "a" * 64,
        "evaluation/timeseries_baseline_results.json",
        "private fixture bytes",
        "OPENAI_API_KEY",
        "sk-synthetic-secret",
    )
    assert all(value not in serialized for value in forbidden)
    assert "Approved bearing condition reference." in serialized
    assert "source_uri" not in serialized
    assert "source_digest" not in serialized


def test_context_uses_top_findings_and_request_local_f_references() -> None:
    prepared = make_prepared()

    assert [(item.finding_id, item.code) for item in prepared.context.findings] == [
        ("F1", "bearing_fault")
    ]
    assert not hasattr(prepared.context.findings[0], "confidence")


def test_context_limits_multimodal_findings_to_deterministic_top_three() -> None:
    machine_id = UUID("00000000-0000-0000-0000-00000000c101")
    machine = Machine(machine_id, "Private multimodal fixture", "rotating_electromechanical_system")
    prediction_specs = (
        (Modality.TIMESERIES, "bearing_fault", 0.90),
        (Modality.AUDIO, "acoustic_anomaly", 0.80),
        (Modality.VISION, "visual_anomaly", 0.70),
        (Modality.THERMAL, "gear_wear_75", 0.95),
    )
    predictions = tuple(Prediction(*spec) for spec in prediction_specs)
    findings = tuple(
        Finding(modality, code, ConditionState.ABNORMAL, confidence, ConfidenceKind.RAW)
        for modality, code, confidence in prediction_specs
    )
    analysis = Analysis(
        id=UUID("00000000-0000-0000-0000-00000000c102"),
        machine_id=machine_id,
        predictions=predictions,
        findings=findings,
        condition=ConditionState.ABNORMAL,
        status=AnalysisStatus.PROVISIONAL,
        health_score=None,
        risk_level=None,
        limitations=(),
        created_at=datetime(2026, 8, 25, 13, 0, tzinfo=UTC),
    )
    sources = (
        structured_source_provenance(Modality.TIMESERIES, {"samples": [1.0]}),
        file_source_provenance(Modality.AUDIO, b"audio", "audio/wav"),
        file_source_provenance(Modality.VISION, b"vision", "image/png"),
        file_source_provenance(Modality.THERMAL, b"thermal", "image/png"),
    )
    package = EvidencePackageService().build(machine, analysis, sources)
    bundle = make_bundle(
        package,
        (
            ChunkSpec("gear_wear_75"),
            ChunkSpec("bearing_fault"),
            ChunkSpec("acoustic_anomaly"),
        ),
    )
    prepared = CopilotContextBuilder().build(
        MaintenanceCopilotRequest(package, bundle, CopilotIntent.EXPLAIN_FINDING)
    )

    assert [(item.finding_id, item.code) for item in prepared.context.findings] == [
        ("F1", "gear_wear_75"),
        ("F2", "bearing_fault"),
        ("F3", "acoustic_anomaly"),
    ]


def test_context_structures_are_frozen() -> None:
    prepared = make_prepared()

    with pytest.raises(FrozenInstanceError):
        prepared.context.asset_type = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        prepared.assigned_citations[0].citation.title = "changed"  # type: ignore[misc]


def test_tampered_evidence_package_is_rejected_before_context() -> None:
    prepared = make_prepared()
    tampered_package = replace(
        prepared.request.evidence_package,
        machine=replace(prepared.request.evidence_package.machine, name="Tampered"),
    )
    request = replace(prepared.request, evidence_package=tampered_package)

    with pytest.raises(CopilotInputError) as error:
        CopilotContextBuilder().build(request)

    assert error.value.code is CopilotInputErrorCode.INVALID_EVIDENCE_PACKAGE
    assert "Tampered" not in str(error.value)


def test_tampered_retrieval_bundle_is_rejected_before_context() -> None:
    prepared = make_prepared()
    original_chunk = prepared.request.retrieval_bundle.chunks[0]
    tampered_bundle = replace(
        prepared.request.retrieval_bundle,
        chunks=(replace(original_chunk, text="Tampered retrieved text"),),
    )

    with pytest.raises(CopilotInputError) as error:
        CopilotContextBuilder().build(replace(prepared.request, retrieval_bundle=tampered_bundle))

    assert error.value.code is CopilotInputErrorCode.INVALID_RETRIEVAL_BUNDLE
    assert "retrieved text" not in str(error.value)


def test_evidence_retrieval_identity_mismatch_is_a_hard_failure() -> None:
    package_a = make_evidence_package("bearing_fault")
    package_b = make_evidence_package("misalignment")
    bundle_b = make_bundle(package_b, (ChunkSpec("misalignment"),))
    request = MaintenanceCopilotRequest(
        package_a,
        bundle_b,
        CopilotIntent.EXPLAIN_FINDING,
    )

    with pytest.raises(CopilotInputError) as error:
        CopilotContextBuilder().build(request)

    assert error.value.code is CopilotInputErrorCode.EVIDENCE_RETRIEVAL_MISMATCH


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("chunk_id", ""),
        ("source_id", " "),
        ("title", ""),
        ("publisher", ""),
        ("section", ""),
        ("source_uri", ""),
        ("fault_code", ""),
        ("asset_type", ""),
        ("source_digest_sha256", "not-a-digest"),
    ],
)
def test_incomplete_citation_metadata_is_a_hard_failure(field: str, value: str) -> None:
    prepared = make_prepared()
    chunk = replace(prepared.request.retrieval_bundle.chunks[0], **{field: value})
    bundle = create_retrieval_bundle(
        evidence_package_id=prepared.request.evidence_package.package_id,
        evidence_package_digest_sha256=(prepared.request.evidence_package.package_digest_sha256),
        corpus_digest_sha256="c" * 64,
        embedding_identity=EMBEDDING_IDENTITY,
        collection_name="copilot_test_collection",
        queries=prepared.request.retrieval_bundle.queries,
        chunks=(chunk,),
    )

    with pytest.raises(CopilotInputError) as error:
        CopilotContextBuilder().build(replace(prepared.request, retrieval_bundle=bundle))

    assert error.value.code is CopilotInputErrorCode.INCOMPLETE_CITATION_METADATA


def test_unknown_matched_intent_is_invalid_bundle_not_a_guessed_lane() -> None:
    prepared = make_prepared()
    chunk = replace(prepared.request.retrieval_bundle.chunks[0], matched_intent="missing")
    bundle = create_retrieval_bundle(
        evidence_package_id=prepared.request.evidence_package.package_id,
        evidence_package_digest_sha256=prepared.request.evidence_package.package_digest_sha256,
        corpus_digest_sha256="c" * 64,
        embedding_identity=EMBEDDING_IDENTITY,
        collection_name="copilot_test_collection",
        queries=prepared.request.retrieval_bundle.queries,
        chunks=(chunk,),
    )

    with pytest.raises(CopilotInputError) as error:
        CopilotContextBuilder().build(replace(prepared.request, retrieval_bundle=bundle))

    assert error.value.code is CopilotInputErrorCode.INVALID_RETRIEVAL_BUNDLE


def test_provider_context_keeps_lane_without_local_url() -> None:
    prepared = make_prepared()
    provider_citation = prepared.context.citations[0]

    assert provider_citation.source_lane is RetrievalLane.MAINTENANCE
    assert set(provider_citation.__dataclass_fields__) == {
        "citation_id",
        "title",
        "publisher",
        "section",
        "fault_code",
        "asset_type",
        "source_lane",
        "text",
    }
