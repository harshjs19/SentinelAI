from dataclasses import FrozenInstanceError, replace
from pathlib import PurePosixPath, PureWindowsPath

import pytest

from ai_core.model_capabilities import (
    MODEL_CAPABILITIES,
    ModelCapability,
    ModelLifecycleStatus,
    get_runtime_default_capability,
    validate_model_capabilities,
)
from ai_core.model_provenance import (
    ProducingModelContext,
    snapshot_producing_model_context,
)
from backend.app.dependencies import _runtime_model_context
from domain.enums.modality import Modality


def test_current_capabilities_have_one_runtime_default_per_modality() -> None:
    validate_model_capabilities(MODEL_CAPABILITIES)

    assert {
        modality: get_runtime_default_capability(modality).model_id for modality in Modality
    } == {
        Modality.TIMESERIES: "timeseries_utk_v1",
        Modality.AUDIO: "audio_mimii_v1",
        Modality.VISION: "vision_visa_pcb1_v1",
        Modality.THERMAL: "thermal_cora_v1",
    }


def test_rejected_audio_v2_is_never_selected_as_runtime_default() -> None:
    selected = get_runtime_default_capability(Modality.AUDIO)
    rejected = next(
        capability
        for capability in MODEL_CAPABILITIES
        if capability.model_id == "audio_mimii_ast_v2"
    )

    assert selected.model_id == "audio_mimii_v1"
    assert rejected.status is ModelLifecycleStatus.REJECTED_EXPERIMENT
    assert rejected.runtime_default is False


@pytest.mark.parametrize(
    ("modality", "model_id"),
    [
        (Modality.TIMESERIES, "timeseries_utk_v1"),
        (Modality.AUDIO, "audio_mimii_v1"),
        (Modality.VISION, "vision_visa_pcb1_v1"),
        (Modality.THERMAL, "thermal_cora_v1"),
    ],
)
def test_runtime_binding_snapshots_the_exact_current_predictor_model(
    modality: Modality,
    model_id: str,
) -> None:
    context = _runtime_model_context(modality, model_id)

    assert context.model_id == model_id
    assert context.modality is modality
    assert context.runtime_default_at_execution is True
    assert not hasattr(context, "artifact_path")
    assert not hasattr(context, "dataset_path")
    assert not hasattr(context, "predictor")


def test_rejected_audio_v2_cannot_bind_as_the_audio_runtime_default() -> None:
    with pytest.raises(RuntimeError, match="does not match the runtime default"):
        _runtime_model_context(Modality.AUDIO, "audio_mimii_ast_v2")


def test_producing_model_context_is_an_immutable_capability_snapshot() -> None:
    capability = get_runtime_default_capability(Modality.VISION)
    context = snapshot_producing_model_context(capability)

    assert context is not capability
    assert context.lifecycle_status is capability.status
    assert context.validated_scope == capability.validated_scope
    with pytest.raises(FrozenInstanceError):
        context.model_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("model_id", [" ", "D:\\models\\model.joblib", "models/model.joblib"])
def test_producing_model_context_rejects_unsafe_identity(model_id: str) -> None:
    with pytest.raises(ValueError, match="path-free"):
        ProducingModelContext(
            model_id=model_id,
            modality=Modality.AUDIO,
            lifecycle_status=ModelLifecycleStatus.EXPERIMENTAL,
            runtime_default_at_execution=False,
            validated_scope="synthetic test scope",
            evaluation_reference="evaluation/test_results.json",
            confidence_semantics="synthetic_score",
        )


def test_confidence_semantics_are_frozen_for_every_declared_model() -> None:
    assert {
        capability.model_id: capability.confidence_semantics for capability in MODEL_CAPABILITIES
    } == {
        "timeseries_utk_v1": "raw_selected_class_predict_proba",
        "audio_mimii_v1": "bounded_empirical_anomaly_evidence_from_normal_calibration",
        "audio_mimii_ast_v2": "bounded_empirical_anomaly_evidence_from_normal_calibration",
        "vision_visa_pcb1_v1": (
            "bounded_empirical_visual_anomaly_evidence_from_normal_calibration"
        ),
        "thermal_cora_v1": "raw_selected_class_predict_proba",
    }


def test_model_ids_are_unique_and_evaluation_references_are_repository_relative() -> None:
    model_ids = [capability.model_id for capability in MODEL_CAPABILITIES]

    assert len(model_ids) == len(set(model_ids))
    for capability in MODEL_CAPABILITIES:
        reference = capability.evaluation_reference
        assert PurePosixPath(reference).parts[0] == "evaluation"
        assert not PurePosixPath(reference).is_absolute()
        assert not PureWindowsPath(reference).is_absolute()
        assert not PureWindowsPath(reference).drive
        assert "\\" not in reference


def test_runtime_default_lookup_rejects_missing_and_multiple_defaults() -> None:
    first = get_runtime_default_capability(Modality.AUDIO)
    second = replace(first, model_id="another_audio_default")

    with pytest.raises(ValueError, match="found 0"):
        get_runtime_default_capability(Modality.AUDIO, ())
    with pytest.raises(ValueError, match="found 2"):
        get_runtime_default_capability(Modality.AUDIO, (first, second))


def test_capability_validation_rejects_duplicate_model_ids() -> None:
    duplicate = replace(MODEL_CAPABILITIES[0], runtime_default=False)

    with pytest.raises(ValueError, match="model IDs must be unique"):
        validate_model_capabilities((*MODEL_CAPABILITIES, duplicate))


@pytest.mark.parametrize(
    "reference",
    [
        "D:/Projects/SentinelAI/evaluation/results.json",
        "D:\\Projects\\SentinelAI\\evaluation\\results.json",
        "/tmp/evaluation/results.json",
        "evaluation/../models/secret.json",
        "docs/results.json",
        "evaluation/results.txt",
    ],
)
def test_capability_rejects_unsafe_evaluation_reference(reference: str) -> None:
    with pytest.raises(ValueError, match="repository-relative"):
        _capability(evaluation_reference=reference)


def test_capability_rejects_blank_confidence_semantics() -> None:
    with pytest.raises(ValueError, match="confidence_semantics"):
        _capability(confidence_semantics=" ")


def _capability(**overrides: object) -> ModelCapability:
    values: dict[str, object] = {
        "model_id": "test_model",
        "modality": Modality.AUDIO,
        "status": ModelLifecycleStatus.EXPERIMENTAL,
        "runtime_default": False,
        "validated_scope": "synthetic test scope",
        "evaluation_reference": "evaluation/test_results.json",
        "confidence_semantics": "synthetic_score",
    }
    values.update(overrides)
    return ModelCapability(**values)  # type: ignore[arg-type]
