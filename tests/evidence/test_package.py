from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from ai_core.model_capabilities import get_runtime_default_capability
from backend.app.services.evidence_package_service import EvidencePackageService
from domain.entities.analysis import Analysis
from domain.entities.finding import Finding
from domain.entities.machine import Machine
from domain.entities.prediction import Prediction
from domain.enums.analysis_limitation import AnalysisLimitation
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from domain.enums.modality import Modality
from domain.enums.risk_level import RiskLevel
from domain.value_objects.health_score import HealthScore
from shared.evidence.models import (
    claim_support_for_analysis,
    create_evidence_package,
    snapshot_analysis,
    snapshot_machine,
    snapshot_model,
    verify_evidence_package_digest,
)
from shared.evidence.provenance import (
    SourceProvenance,
    file_source_provenance,
    structured_source_provenance,
)

MACHINE_ID = UUID("00000000-0000-0000-0000-000000000101")
ANALYSIS_ID = UUID("00000000-0000-0000-0000-000000000201")
CREATED_AT = datetime(2026, 8, 25, 8, 30, 0, 123456, tzinfo=UTC)


@pytest.mark.parametrize(
    ("modality", "label", "expected_model_id"),
    [
        (Modality.TIMESERIES, "bearing_fault", "timeseries_utk_v1"),
        (Modality.AUDIO, "acoustic_anomaly", "audio_mimii_v1"),
        (Modality.VISION, "visual_anomaly", "vision_visa_pcb1_v1"),
        (Modality.THERMAL, "gear_wear_75", "thermal_cora_v1"),
    ],
)
def test_abnormal_single_modality_claim_boundaries_and_runtime_model_mapping(
    modality: Modality,
    label: str,
    expected_model_id: str,
) -> None:
    analysis = _analysis(modality, label, confidence=0.99)

    package = EvidencePackageService().build(
        _machine(),
        analysis,
        [_source(modality, b"synthetic source")],
    )

    assert package.claim_support.condition_available is True
    assert package.claim_support.failure_probability_available is False
    assert package.claim_support.fault_severity_available is False
    assert package.claim_support.health_score_available is False
    assert package.claim_support.operational_risk_available is False
    assert package.models[0].model_id == expected_model_id
    assert package.models[0].status is get_runtime_default_capability(modality).status
    assert package.models[0].runtime_default is True
    assert package.analysis.predictions == analysis.predictions
    assert package.analysis.findings == analysis.findings
    assert package.analysis.limitations == analysis.limitations


def test_health_and_risk_availability_only_reflect_existing_analysis_values() -> None:
    analysis = _analysis(
        Modality.TIMESERIES,
        "bearing_fault",
        health_score=HealthScore(42),
        risk_level=RiskLevel.HIGH,
    )

    package = EvidencePackageService().build(
        _machine(), analysis, [_source(Modality.TIMESERIES, b"window")]
    )

    assert package.analysis.health_score == 42
    assert package.analysis.risk_level is RiskLevel.HIGH
    assert package.claim_support.health_score_available is True
    assert package.claim_support.operational_risk_available is True


def test_insufficient_evidence_builds_without_source_or_model_provenance() -> None:
    analysis = Analysis(
        id=ANALYSIS_ID,
        machine_id=MACHINE_ID,
        predictions=(),
        findings=(),
        condition=ConditionState.INDETERMINATE,
        status=AnalysisStatus.INSUFFICIENT_EVIDENCE,
        health_score=None,
        risk_level=None,
        limitations=(),
        created_at=CREATED_AT,
    )

    package = EvidencePackageService().build(_machine(), analysis, [])

    assert package.sources == ()
    assert package.models == ()
    assert package.claim_support.condition_available is False
    assert package.claim_support.health_score_available is False
    assert package.claim_support.operational_risk_available is False
    assert verify_evidence_package_digest(package)


def test_same_inputs_produce_same_digest_and_package_id() -> None:
    analysis = _analysis(Modality.TIMESERIES, "bearing_fault")
    source = _source(Modality.TIMESERIES, b"same window")
    service = EvidencePackageService()

    first = service.build(_machine(), analysis, [source])
    second = service.build(_machine(), analysis, [source])

    assert first == second
    assert first.package_digest_sha256 == second.package_digest_sha256
    assert first.package_id == second.package_id
    assert first.package_id == f"evp1_{first.package_digest_sha256[:32]}"
    assert verify_evidence_package_digest(first)


def test_identity_changes_with_source_analysis_machine_or_model_provenance() -> None:
    analysis = _analysis(Modality.TIMESERIES, "bearing_fault")
    service = EvidencePackageService()
    original = service.build(_machine(), analysis, [_source(Modality.TIMESERIES, b"source one")])
    changed_source = service.build(
        _machine(), analysis, [_source(Modality.TIMESERIES, b"source two")]
    )
    changed_analysis = service.build(
        _machine(),
        replace(analysis, id=UUID("00000000-0000-0000-0000-000000000202")),
        [_source(Modality.TIMESERIES, b"source one")],
    )
    changed_machine = service.build(
        replace(_machine(), name="Changed machine"),
        analysis,
        [_source(Modality.TIMESERIES, b"source one")],
    )
    changed_model_snapshot = replace(original.models[0], validated_scope="changed scope")
    changed_model = create_evidence_package(
        machine=original.machine,
        analysis=original.analysis,
        sources=original.sources,
        models=(changed_model_snapshot,),
        claim_support=original.claim_support,
    )

    changed_packages = (changed_source, changed_analysis, changed_machine, changed_model)
    assert all(
        item.package_digest_sha256 != original.package_digest_sha256 for item in changed_packages
    )
    assert all(item.package_id != original.package_id for item in changed_packages)


def test_integrity_verification_detects_tampered_snapshot_with_old_identity() -> None:
    package = EvidencePackageService().build(
        _machine(),
        _analysis(Modality.VISION, "visual_anomaly"),
        [_source(Modality.VISION, b"image")],
    )
    tampered = replace(package, machine=replace(package.machine, name="Tampered"))

    assert verify_evidence_package_digest(package)
    assert not verify_evidence_package_digest(tampered)
    with pytest.raises(FrozenInstanceError):
        package.package_id = "changed"  # type: ignore[misc]


def test_new_provenance_collections_sort_without_changing_analysis_order() -> None:
    analysis = _multimodal_analysis()
    audio_source = _source(Modality.AUDIO, b"audio")
    timeseries_source = _source(Modality.TIMESERIES, b"samples")

    package = EvidencePackageService().build(
        _machine(), analysis, [timeseries_source, audio_source]
    )

    assert [item.modality for item in package.analysis.predictions] == [
        Modality.TIMESERIES,
        Modality.AUDIO,
    ]
    assert [item.modality for item in package.sources] == [Modality.AUDIO, Modality.TIMESERIES]
    assert [item.modality for item in package.models] == [Modality.AUDIO, Modality.TIMESERIES]


def test_service_rejects_machine_source_and_duplicate_provenance_mismatches() -> None:
    analysis = _analysis(Modality.VISION, "visual_anomaly")
    source = _source(Modality.VISION, b"image")
    service = EvidencePackageService()

    with pytest.raises(ValueError, match="Machine ID"):
        service.build(
            replace(_machine(), id=UUID("00000000-0000-0000-0000-000000000999")),
            analysis,
            [source],
        )
    with pytest.raises(ValueError, match="must match Analysis predictions"):
        service.build(_machine(), analysis, [_source(Modality.AUDIO, b"audio")])
    with pytest.raises(ValueError, match="Duplicate source"):
        service.build(_machine(), analysis, [source, source])


def test_service_rejects_duplicate_prediction_modalities() -> None:
    prediction = Prediction(Modality.AUDIO, "acoustic_anomaly", 0.9)
    finding = Finding(
        modality=Modality.AUDIO,
        code="acoustic_anomaly",
        condition=ConditionState.ABNORMAL,
        confidence=0.9,
        confidence_kind=ConfidenceKind.RAW,
    )
    analysis = Analysis(
        id=ANALYSIS_ID,
        machine_id=MACHINE_ID,
        predictions=(prediction, prediction),
        findings=(finding, finding),
        condition=ConditionState.ABNORMAL,
        status=AnalysisStatus.PROVISIONAL,
        health_score=None,
        risk_level=None,
        limitations=(),
        created_at=CREATED_AT,
    )

    with pytest.raises(ValueError, match="duplicate prediction"):
        EvidencePackageService().build(_machine(), analysis, [_source(Modality.AUDIO, b"audio")])


def test_service_rejects_wrong_source_kind_for_modality() -> None:
    analysis = _analysis(Modality.TIMESERIES, "bearing_fault")
    wrong_kind = file_source_provenance(
        Modality.TIMESERIES,
        b"not canonical structured input",
        "application/json",
    )

    with pytest.raises(ValueError, match="timeseries source must use structured"):
        EvidencePackageService().build(_machine(), analysis, [wrong_kind])


def test_pure_builder_snapshots_capability_instead_of_holding_live_declaration() -> None:
    analysis = _analysis(Modality.THERMAL, "gear_wear_75")
    analysis_snapshot = snapshot_analysis(analysis)
    capability = get_runtime_default_capability(Modality.THERMAL)
    model = snapshot_model(capability)

    package = create_evidence_package(
        machine=snapshot_machine(_machine()),
        analysis=analysis_snapshot,
        sources=(_source(Modality.THERMAL, b"thermal image"),),
        models=(model,),
        claim_support=claim_support_for_analysis(analysis_snapshot),
    )

    assert package.models[0] is not capability
    assert package.models[0].model_id == capability.model_id
    assert package.models[0].validated_scope == capability.validated_scope


def test_pure_builder_rejects_duplicate_models_and_unsupported_claims() -> None:
    original = EvidencePackageService().build(
        _machine(),
        _analysis(Modality.AUDIO, "acoustic_anomaly"),
        [_source(Modality.AUDIO, b"audio")],
    )

    with pytest.raises(ValueError, match="duplicate model"):
        create_evidence_package(
            machine=original.machine,
            analysis=original.analysis,
            sources=original.sources,
            models=(original.models[0], original.models[0]),
            claim_support=original.claim_support,
        )
    with pytest.raises(ValueError, match="claim support is inconsistent"):
        create_evidence_package(
            machine=original.machine,
            analysis=original.analysis,
            sources=original.sources,
            models=original.models,
            claim_support=replace(
                original.claim_support,
                failure_probability_available=True,
            ),
        )


def _machine() -> Machine:
    return Machine(id=MACHINE_ID, name="Synthetic pump", asset_type="pump")


def _analysis(
    modality: Modality,
    label: str,
    *,
    confidence: float = 0.91,
    health_score: HealthScore | None = None,
    risk_level: RiskLevel | None = None,
) -> Analysis:
    prediction = Prediction(modality=modality, label=label, confidence=confidence)
    finding = Finding(
        modality=modality,
        code=label,
        condition=ConditionState.ABNORMAL,
        confidence=confidence,
        confidence_kind=ConfidenceKind.RAW,
    )
    return Analysis(
        id=ANALYSIS_ID,
        machine_id=MACHINE_ID,
        predictions=(prediction,),
        findings=(finding,),
        condition=ConditionState.ABNORMAL,
        status=AnalysisStatus.PROVISIONAL,
        health_score=health_score,
        risk_level=risk_level,
        limitations=(
            AnalysisLimitation.UNCALIBRATED_CONFIDENCE,
            AnalysisLimitation.FAULT_SEVERITY_UNAVAILABLE,
            AnalysisLimitation.RISK_CONTEXT_UNAVAILABLE,
            AnalysisLimitation.SINGLE_MODALITY_EVIDENCE,
        ),
        created_at=CREATED_AT,
    )


def _multimodal_analysis() -> Analysis:
    predictions = (
        Prediction(Modality.TIMESERIES, "bearing_fault", 0.91),
        Prediction(Modality.AUDIO, "acoustic_anomaly", 0.82),
    )
    findings = tuple(
        Finding(
            modality=prediction.modality,
            code=prediction.label,
            condition=ConditionState.ABNORMAL,
            confidence=prediction.confidence,
            confidence_kind=ConfidenceKind.RAW,
        )
        for prediction in predictions
    )
    return Analysis(
        id=ANALYSIS_ID,
        machine_id=MACHINE_ID,
        predictions=predictions,
        findings=findings,
        condition=ConditionState.ABNORMAL,
        status=AnalysisStatus.PROVISIONAL,
        health_score=None,
        risk_level=None,
        limitations=(AnalysisLimitation.FAULT_SEVERITY_UNAVAILABLE,),
        created_at=CREATED_AT,
    )


def _source(modality: Modality, content: bytes) -> SourceProvenance:
    if modality is Modality.TIMESERIES:
        return structured_source_provenance(
            modality,
            {"samples": [{"value": float(byte)} for byte in content]},
        )
    content_types = {
        Modality.AUDIO: "audio/wav",
        Modality.VISION: "image/png",
        Modality.THERMAL: "image/png",
    }
    return file_source_provenance(modality, content, content_types[modality])
