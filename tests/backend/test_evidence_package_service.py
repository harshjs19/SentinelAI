import builtins
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

import ai_core.model_capabilities as model_capabilities
import backend.app.dependencies as dependencies
from ai_core.model_capabilities import get_runtime_default_capability
from ai_core.model_provenance import (
    ProducingModelContext,
    snapshot_producing_model_context,
)
from backend.app.services.evidence_package_service import (
    EvidencePackageService,
    ProducingModelProvenanceUnavailable,
)
from domain.entities.analysis import Analysis
from domain.entities.finding import Finding
from domain.entities.machine import Machine
from domain.entities.prediction import Prediction
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from domain.enums.modality import Modality
from inference.orchestrator import InferenceOrchestrator
from modules.decision.engine import DecisionEngine
from shared.evidence.models import verify_evidence_package_digest
from shared.evidence.provenance import (
    SourceProvenance,
    file_source_provenance,
    structured_source_provenance,
)


def test_service_builds_without_models_decision_engine_database_or_file_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("EvidencePackageService crossed an external runtime boundary")

    for provider_name in (
        "get_timeseries_predictor",
        "get_audio_predictor",
        "get_vision_predictor",
        "get_thermal_predictor",
        "get_inference_orchestrator",
        "get_decision_engine",
        "get_machine_service",
    ):
        monkeypatch.setattr(dependencies, provider_name, unexpected_call)
    monkeypatch.setattr(InferenceOrchestrator, "predict", unexpected_call)
    monkeypatch.setattr(DecisionEngine, "evaluate", unexpected_call)

    machine_id = UUID("00000000-0000-0000-0000-000000000301")
    prediction = Prediction(Modality.TIMESERIES, "bearing_fault", 0.88)
    analysis = Analysis(
        id=UUID("00000000-0000-0000-0000-000000000302"),
        machine_id=machine_id,
        predictions=(prediction,),
        findings=(
            Finding(
                modality=prediction.modality,
                code=prediction.label,
                condition=ConditionState.ABNORMAL,
                confidence=prediction.confidence,
                confidence_kind=ConfidenceKind.RAW,
            ),
        ),
        condition=ConditionState.ABNORMAL,
        status=AnalysisStatus.PROVISIONAL,
        health_score=None,
        risk_level=None,
        limitations=(),
        created_at=datetime(2026, 8, 25, 9, 0, tzinfo=UTC),
    )
    source = structured_source_provenance(
        Modality.TIMESERIES,
        {"samples": [{"ch1": 1.0}, {"ch1": 2.0}]},
    )
    monkeypatch.setattr(builtins, "open", unexpected_call)

    package = EvidencePackageService().build(
        Machine(machine_id, "Synthetic motor", "motor"),
        analysis,
        [source],
        producing_models=(
            snapshot_producing_model_context(get_runtime_default_capability(Modality.TIMESERIES)),
        ),
    )

    assert package.models[0].model_id == "timeseries_utk_v1"
    assert package.models[0].evaluation_reference == ("evaluation/timeseries_baseline_results.json")
    assert verify_evidence_package_digest(package)


def test_captured_vision_model_survives_a_later_runtime_default_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = _analysis(Modality.VISION, "visual_anomaly")
    captured = _model_context(Modality.VISION)
    later_default = replace(
        get_runtime_default_capability(Modality.VISION),
        model_id="vision_v2",
    )
    monkeypatch.setattr(
        model_capabilities,
        "get_runtime_default_capability",
        lambda _modality: later_default,
    )

    package = EvidencePackageService().build(
        _machine(),
        analysis,
        [_source(Modality.VISION)],
        producing_models=(captured,),
    )

    assert package.models[0].model_id == "vision_visa_pcb1_v1"
    assert package.models[0].model_id != later_default.model_id


def test_evidence_bearing_analysis_fails_closed_without_producing_context() -> None:
    analysis = _analysis(Modality.VISION, "visual_anomaly")

    with pytest.raises(ProducingModelProvenanceUnavailable, match="Exact producing-model"):
        EvidencePackageService().build(
            _machine(),
            analysis,
            [_source(Modality.VISION)],
        )


def test_wrong_producing_context_modality_is_rejected() -> None:
    analysis = _analysis(Modality.VISION, "visual_anomaly")

    with pytest.raises(ValueError, match="modalities must match Analysis predictions"):
        EvidencePackageService().build(
            _machine(),
            analysis,
            [_source(Modality.VISION)],
            producing_models=(_model_context(Modality.AUDIO),),
        )


def test_duplicate_producing_context_modality_is_rejected() -> None:
    analysis = _analysis(Modality.VISION, "visual_anomaly")
    context = _model_context(Modality.VISION)

    with pytest.raises(ValueError, match="Duplicate producing-model"):
        EvidencePackageService().build(
            _machine(),
            analysis,
            [_source(Modality.VISION)],
            producing_models=(context, context),
        )


def test_extra_producing_context_is_rejected() -> None:
    analysis = _analysis(Modality.TIMESERIES, "bearing_fault")

    with pytest.raises(ValueError, match="modalities absent from Analysis"):
        EvidencePackageService().build(
            _machine(),
            analysis,
            [_source(Modality.TIMESERIES)],
            producing_models=(
                _model_context(Modality.TIMESERIES),
                _model_context(Modality.VISION),
            ),
        )


def test_producing_model_id_changes_evidence_package_identity() -> None:
    analysis = _analysis(Modality.VISION, "visual_anomaly")
    source = _source(Modality.VISION)
    original_context = _model_context(Modality.VISION)
    changed_context = replace(original_context, model_id="vision_v2")
    service = EvidencePackageService()

    original = service.build(_machine(), analysis, [source], producing_models=(original_context,))
    repeated = service.build(_machine(), analysis, [source], producing_models=(original_context,))
    changed = service.build(_machine(), analysis, [source], producing_models=(changed_context,))

    assert repeated.package_digest_sha256 == original.package_digest_sha256
    assert repeated.package_id == original.package_id
    assert changed.package_digest_sha256 != original.package_digest_sha256
    assert changed.package_id != original.package_id


def test_nondefault_producing_status_is_preserved_as_execution_metadata() -> None:
    analysis = _analysis(Modality.VISION, "visual_anomaly")
    context = replace(
        _model_context(Modality.VISION),
        model_id="vision_previous",
        runtime_default_at_execution=False,
    )

    package = EvidencePackageService().build(
        _machine(),
        analysis,
        [_source(Modality.VISION)],
        producing_models=(context,),
    )

    assert package.models[0].model_id == "vision_previous"
    assert package.models[0].runtime_default is False


def _machine() -> Machine:
    return Machine(
        UUID("00000000-0000-0000-0000-000000000401"),
        "Synthetic provenance machine",
        "rotating_electromechanical_system",
    )


def _analysis(modality: Modality, label: str) -> Analysis:
    machine = _machine()
    prediction = Prediction(modality, label, 0.88)
    finding = Finding(
        modality=modality,
        code=label,
        condition=ConditionState.ABNORMAL,
        confidence=prediction.confidence,
        confidence_kind=ConfidenceKind.RAW,
    )
    return Analysis(
        id=UUID("00000000-0000-0000-0000-000000000402"),
        machine_id=machine.id,
        predictions=(prediction,),
        findings=(finding,),
        condition=ConditionState.ABNORMAL,
        status=AnalysisStatus.PROVISIONAL,
        health_score=None,
        risk_level=None,
        limitations=(),
        created_at=datetime(2026, 8, 26, 8, 0, tzinfo=UTC),
    )


def _source(modality: Modality) -> SourceProvenance:
    if modality is Modality.TIMESERIES:
        return structured_source_provenance(modality, {"samples": [{"value": 1.0}]})
    return file_source_provenance(modality, b"synthetic source", "image/png")


def _model_context(modality: Modality) -> ProducingModelContext:
    return snapshot_producing_model_context(get_runtime_default_capability(modality))
