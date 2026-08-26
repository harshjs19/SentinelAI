import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID

import pytest

from ai_core.model_capabilities import get_runtime_default_capability
from ai_core.model_provenance import snapshot_producing_model_context
from backend.app.schemas.evidence import EvidencePackageSchema
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
from shared.evidence.provenance import file_source_provenance, structured_source_provenance

MACHINE_ID = UUID("00000000-0000-0000-0000-000000000101")
ANALYSIS_ID = UUID("00000000-0000-0000-0000-000000000201")
CREATED_AT = datetime(2026, 8, 25, 8, 30, 0, 123456, tzinfo=UTC)


def test_schema_serialization_matches_the_frozen_v1_json_contract() -> None:
    schema = EvidencePackageSchema.from_domain(_timeseries_package())

    assert schema.model_dump(mode="json") == {
        "schema_version": "1",
        "package_id": "evp1_fd60a29ac823915f6e98e14e3981c11c",
        "package_digest_sha256": (
            "fd60a29ac823915f6e98e14e3981c11cad826556c67a5f0f4e588ca20daeb74e"
        ),
        "created_at": "2026-08-25T08:30:00.123456Z",
        "machine": {
            "machine_id": "00000000-0000-0000-0000-000000000101",
            "name": "Synthetic pump",
            "asset_type": "pump",
        },
        "analysis": {
            "analysis_id": "00000000-0000-0000-0000-000000000201",
            "machine_id": "00000000-0000-0000-0000-000000000101",
            "predictions": [
                {
                    "modality": "timeseries",
                    "label": "bearing_fault",
                    "confidence": 0.91,
                }
            ],
            "findings": [
                {
                    "modality": "timeseries",
                    "code": "bearing_fault",
                    "condition": "abnormal",
                    "confidence": 0.91,
                    "confidence_kind": "raw",
                }
            ],
            "condition": "abnormal",
            "status": "provisional",
            "health_score": None,
            "risk_level": None,
            "limitations": [
                "uncalibrated_confidence",
                "fault_severity_unavailable",
                "risk_context_unavailable",
                "single_modality_evidence",
            ],
            "created_at": "2026-08-25T08:30:00.123456Z",
            "top_findings": [
                {
                    "modality": "timeseries",
                    "code": "bearing_fault",
                    "condition": "abnormal",
                    "confidence": 0.91,
                    "confidence_kind": "raw",
                }
            ],
        },
        "sources": [
            {
                "modality": "timeseries",
                "source_kind": "structured",
                "sha256": "2af763b6a2599ba5e5fc32e8cb18a9e2c276ace8eb97116a8e813803d44617d6",
                "size_bytes": 37,
                "content_type": "application/json",
            }
        ],
        "models": [
            {
                "model_id": "timeseries_utk_v1",
                "modality": "timeseries",
                "status": "validated_baseline",
                "runtime_default": True,
                "validated_scope": (
                    "UTK blocked chronological within-recording multiclass evaluation"
                ),
                "evaluation_reference": "evaluation/timeseries_baseline_results.json",
                "confidence_semantics": "raw_selected_class_predict_proba",
            }
        ],
        "claim_support": {
            "condition_available": True,
            "failure_probability_available": False,
            "fault_severity_available": False,
            "health_score_available": False,
            "operational_risk_available": False,
        },
    }


def test_serialized_package_is_small_frozen_and_excludes_raw_sources_and_local_paths() -> None:
    raw_secret = b"RAW_UPLOAD_SECRET_DO_NOT_SERIALIZE"
    prediction = Prediction(Modality.VISION, "visual_anomaly", 0.8)
    analysis = _analysis(prediction)
    package = EvidencePackageService().build(
        _machine(),
        analysis,
        [file_source_provenance(Modality.VISION, raw_secret, "image/png")],
        producing_models=(
            snapshot_producing_model_context(get_runtime_default_capability(Modality.VISION)),
        ),
    )
    schema = EvidencePackageSchema.from_domain(package)
    serialized = schema.model_dump_json()

    assert len(serialized.encode("utf-8")) < 4_096
    assert raw_secret.decode() not in serialized
    assert "base64" not in serialized.lower()
    assert "D:\\Projects" not in serialized
    assert "/tmp/" not in serialized
    assert "models/" not in serialized
    assert "datasets/" not in serialized
    assert json.loads(serialized)["sources"][0].keys() == {
        "modality",
        "source_kind",
        "sha256",
        "size_bytes",
        "content_type",
    }
    with pytest.raises((FrozenInstanceError, ValueError)):
        schema.package_id = "changed"  # type: ignore[misc]


def test_structured_raw_sample_values_are_not_serialized() -> None:
    marker = "RAW_STRUCTURED_SAMPLE_SECRET_DO_NOT_SERIALIZE"
    package = EvidencePackageService().build(
        _machine(),
        _analysis(Prediction(Modality.TIMESERIES, "bearing_fault", 0.91)),
        [
            structured_source_provenance(
                Modality.TIMESERIES,
                {"samples": [{"marker": marker, "value": 1.0}]},
            )
        ],
        producing_models=(
            snapshot_producing_model_context(get_runtime_default_capability(Modality.TIMESERIES)),
        ),
    )

    assert marker not in EvidencePackageSchema.from_domain(package).model_dump_json()


@pytest.mark.parametrize(
    ("modality", "label", "content_type"),
    [
        (Modality.AUDIO, "acoustic_anomaly", "audio/wav"),
        (Modality.VISION, "visual_anomaly", "image/jpeg"),
        (Modality.THERMAL, "gear_wear_75", "image/png"),
    ],
)
def test_uploaded_media_bytes_are_not_serialized(
    modality: Modality,
    label: str,
    content_type: str,
) -> None:
    raw_marker = f"RAW_{modality.value.upper()}_PAYLOAD_DO_NOT_SERIALIZE".encode()
    package = EvidencePackageService().build(
        _machine(),
        _analysis(Prediction(modality, label, 0.8)),
        [file_source_provenance(modality, raw_marker, content_type)],
        producing_models=(
            snapshot_producing_model_context(get_runtime_default_capability(modality)),
        ),
    )

    assert raw_marker.decode() not in EvidencePackageSchema.from_domain(package).model_dump_json()


def _timeseries_package():
    return EvidencePackageService().build(
        _machine(),
        _analysis(Prediction(Modality.TIMESERIES, "bearing_fault", 0.91)),
        [
            structured_source_provenance(
                Modality.TIMESERIES,
                {"samples": [{"ch1": 1.0}, {"ch1": 2.0}]},
            )
        ],
        producing_models=(
            snapshot_producing_model_context(get_runtime_default_capability(Modality.TIMESERIES)),
        ),
    )


def _machine() -> Machine:
    return Machine(MACHINE_ID, "Synthetic pump", "pump")


def _analysis(prediction: Prediction) -> Analysis:
    finding = Finding(
        modality=prediction.modality,
        code=prediction.label,
        condition=ConditionState.ABNORMAL,
        confidence=prediction.confidence,
        confidence_kind=ConfidenceKind.RAW,
    )
    return Analysis(
        id=ANALYSIS_ID,
        machine_id=MACHINE_ID,
        predictions=(prediction,),
        findings=(finding,),
        condition=ConditionState.ABNORMAL,
        status=AnalysisStatus.PROVISIONAL,
        health_score=None,
        risk_level=None,
        limitations=(
            AnalysisLimitation.UNCALIBRATED_CONFIDENCE,
            AnalysisLimitation.FAULT_SEVERITY_UNAVAILABLE,
            AnalysisLimitation.RISK_CONTEXT_UNAVAILABLE,
            AnalysisLimitation.SINGLE_MODALITY_EVIDENCE,
        ),
        created_at=CREATED_AT,
    )
