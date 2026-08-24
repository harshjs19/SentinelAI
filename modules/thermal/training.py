import json
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sklearn.pipeline import Pipeline

from modules.thermal.artifact import (
    THERMAL_ARTIFACT_FORMAT_VERSION,
    ThermalArtifactMetadata,
    ThermalModelArtifact,
    save_thermal_artifact,
)
from modules.thermal.config import (
    CONDITION_LABELS,
    DATASET_DOI,
    DATASET_LICENSE,
    DATASET_SOURCE,
    DATASET_VERSION,
    SPEED_RPM,
    SUPPORTED_ASSET_TYPES,
    TEST_SPEEDS,
    TRAIN_SPEEDS,
    VALIDATION_SPEEDS,
    ThermalTrainingConfig,
)
from modules.thermal.embedding_cache import ThermalEmbeddingData, load_or_extract_embeddings
from modules.thermal.encoder import FrozenThermalResNet18Encoder
from modules.thermal.evaluation import (
    aligned_probabilities,
    classification_metrics,
    experiment_level_metrics,
)
from modules.thermal.modeling import candidate_factories, model_parameters, select_candidate


@dataclass(frozen=True)
class ThermalFitResult:
    selected_model: str
    final_model: Any
    candidate_models: dict[str, Any]
    candidate_parameters: dict[str, dict[str, object]]
    validation_metrics: dict[str, dict[str, object]]
    final_test_metrics: dict[str, object]
    experiment_test_metrics: dict[str, object]


def fit_select_refit(
    data: ThermalEmbeddingData,
    factories: Mapping[str, Callable[[], Any]],
    labels: tuple[str, ...] = tuple(CONDITION_LABELS.values()),
) -> ThermalFitResult:
    train_mask = np.isin(data.speeds, TRAIN_SPEEDS)
    validation_mask = np.isin(data.speeds, VALIDATION_SPEEDS)
    test_mask = np.isin(data.speeds, TEST_SPEEDS)
    _validate_partitions(data, train_mask, validation_mask, test_mask)

    candidate_models: dict[str, Any] = {}
    candidate_parameters: dict[str, dict[str, object]] = {}
    validation_metrics: dict[str, dict[str, object]] = {}
    for name, factory in factories.items():
        model = factory()
        model.fit(data.embeddings[train_mask], data.labels[train_mask])
        probabilities = aligned_probabilities(model, data.embeddings[validation_mask], labels)
        candidate_models[name] = model
        candidate_parameters[name] = (
            model_parameters(model)
            if isinstance(model, Pipeline)
            else {"model": type(model).__name__}
        )
        validation_metrics[name] = classification_metrics(
            data.labels[validation_mask], probabilities, labels
        )

    selected_model = select_candidate(validation_metrics)
    final_model = factories[selected_model]()
    final_fit_mask = train_mask | validation_mask
    final_model.fit(data.embeddings[final_fit_mask], data.labels[final_fit_mask])
    test_probabilities = aligned_probabilities(final_model, data.embeddings[test_mask], labels)
    return ThermalFitResult(
        selected_model=selected_model,
        final_model=final_model,
        candidate_models=candidate_models,
        candidate_parameters=candidate_parameters,
        validation_metrics=validation_metrics,
        final_test_metrics=classification_metrics(
            data.labels[test_mask], test_probabilities, labels
        ),
        experiment_test_metrics=experiment_level_metrics(
            data.labels[test_mask],
            test_probabilities,
            data.experiment_ids[test_mask],
            labels,
        ),
    )


def train_thermal_baseline(config: ThermalTrainingConfig) -> dict[str, object]:
    encoder = FrozenThermalResNet18Encoder(config.encoder_path, config.device)
    data = load_or_extract_embeddings(
        config.dataset_root.resolve(),
        config.embedding_cache_path,
        encoder,
        config.batch_size,
    )
    result = fit_select_refit(data, candidate_factories(config.random_seed))
    manifest = _load_manifest(config.dataset_root)
    split = {
        "protocol": "predeclared operating-speed-held-out split; no random frame split",
        "train_speeds": list(TRAIN_SPEEDS),
        "validation_speeds": list(VALIDATION_SPEEDS),
        "locked_test_speeds": list(TEST_SPEEDS),
        "candidate_selection": "F50 frame-level validation macro F1; balanced accuracy tie-break",
        "final_refit": "fresh selected model fit on F5 + F15 + F50",
        "locked_test_evaluation": "F60 evaluated exactly once after final refit",
    }
    counts = _training_counts(data)
    metadata = ThermalArtifactMetadata(
        format_version=THERMAL_ARTIFACT_FORMAT_VERSION,
        dataset_doi=DATASET_DOI,
        dataset_version=DATASET_VERSION,
        dataset_license=DATASET_LICENSE,
        dataset_files=tuple(manifest["files"]),
        data_representation=(
            "240x320x3 uint8 RGB arrays with replicated grayscale channels; "
            "non-radiometric thermographic appearance"
        ),
        condition_mapping=CONDITION_LABELS,
        speed_rpm_mapping=SPEED_RPM,
        split=split,
        supported_asset_types=SUPPORTED_ASSET_TYPES,
        preprocessing=encoder.metadata.preprocessing,
        encoder=encoder.metadata,
        embedding_dimension=encoder.metadata.global_dimension,
        candidate_parameters=result.candidate_parameters,
        validation_metrics=result.validation_metrics,
        selection_metric="F50 frame-level macro F1",
        selected_model=result.selected_model,
        final_fit_speeds=TRAIN_SPEEDS + VALIDATION_SPEEDS,
        locked_test_speed=TEST_SPEEDS[0],
        final_test_metrics=result.final_test_metrics,
        experiment_test_metrics=result.experiment_test_metrics,
        training_counts=counts,
        confidence_semantics=(
            "raw selected-class classifier predict_proba output; not calibrated severity, "
            "failure probability, health, or operational risk"
        ),
    )
    artifact = ThermalModelArtifact(result.final_model, metadata)
    save_thermal_artifact(artifact, config.artifact_path)
    metadata_path = config.artifact_path.with_suffix(".metadata.json")
    metadata_path.write_text(
        json.dumps(metadata.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    evaluation = {
        "dataset": {
            "title": "Rotating electromechanical system dataset for condition monitoring",
            "doi": DATASET_DOI,
            "version": DATASET_VERSION,
            "license": DATASET_LICENSE,
            "source": DATASET_SOURCE,
            "downloaded_files": manifest["files"],
            "selected_bytes": manifest["selection"]["selected_bytes"],
            "data_representation": metadata.data_representation,
            "mat_structure": {
                "format": "MATLAB 5.0",
                "variable": "imagenes_celda",
                "variable_shape": [1, 450],
                "variable_type": "cell",
                "frame_shape": [240, 320, 3],
                "dtype": "uint8",
                "channels": "three identical grayscale channels stored as RGB",
                "radiometric_temperature": False,
            },
        },
        "conditions": CONDITION_LABELS,
        "speeds_rpm": SPEED_RPM,
        "split": split,
        "counts": counts,
        "leakage_audit": data.audit,
        "preprocessing": encoder.metadata.preprocessing,
        "encoder": {
            **encoder.metadata.to_dict(),
            "frozen": True,
            "device": encoder.device,
            "classifier_logits_used": False,
        },
        "embedding_cache": {
            "path": str(config.embedding_cache_path),
            "cache_hit": data.cache_hit,
            "bytes": config.embedding_cache_path.stat().st_size,
            "extraction_seconds": data.extraction_seconds,
            "frame_count": len(data.labels),
        },
        "candidate_models": result.candidate_parameters,
        "validation_metrics": result.validation_metrics,
        "selected_model": result.selected_model,
        "final_fit": {
            "fresh_instance": True,
            "speeds": list(metadata.final_fit_speeds),
            "frame_count": int(np.isin(data.speeds, metadata.final_fit_speeds).sum()),
        },
        "final_test_metrics": result.final_test_metrics,
        "experiment_level_metrics": result.experiment_test_metrics,
        "artifact": {
            "path": str(config.artifact_path),
            "bytes": config.artifact_path.stat().st_size,
            "format_version": THERMAL_ARTIFACT_FORMAT_VERSION,
            "metadata_path": str(metadata_path),
            "encoder_stored_inside_artifact": False,
        },
        "confidence": {
            "kind": "raw",
            "definition": metadata.confidence_semantics,
            "cross_modally_comparable": False,
        },
        "runtime": {
            "device": encoder.device,
            "resnet_weights_bytes": encoder.metadata.weights_bytes,
        },
        "limitations": [
            "Frame metrics are temporally correlated and do not represent independent experiments",
            "F60 contains nine independent condition-speed acquisitions, one per class",
            "Speed holdout measures domain shift on the same test bench and fault configuration",
            (
                "No unseen-machine, unseen-camera, unseen-installation, or plant "
                "generalization is proven"
            ),
            "Component disassembly and reassembly can confound condition-specific appearance",
            "RGB values are thermographic appearance, not calibrated Celsius temperature",
            "Raw classifier confidence is not severity, failure probability, health, or risk",
            "No confidence calibration or multimodal fusion",
            "Raspberry Pi 4 performance has not been measured",
        ],
    }
    config.evaluation_path.parent.mkdir(parents=True, exist_ok=True)
    config.evaluation_path.write_text(
        json.dumps(evaluation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evaluation


def _validate_partitions(
    data: ThermalEmbeddingData,
    train_mask: NDArray[np.bool_],
    validation_mask: NDArray[np.bool_],
    test_mask: NDArray[np.bool_],
) -> None:
    if (
        np.any(train_mask & validation_mask)
        or np.any(train_mask & test_mask)
        or np.any(validation_mask & test_mask)
    ):
        raise ValueError("Thermal speed partitions must be disjoint")
    if not np.all(train_mask | validation_mask | test_mask):
        raise ValueError("Every Thermal frame must belong to the declared speed split")
    for mask in (train_mask, validation_mask, test_mask):
        if not mask.any() or set(data.labels[mask]) != set(CONDITION_LABELS.values()):
            raise ValueError("Every Thermal split must contain all condition classes")
    for experiment_id in set(data.experiment_ids):
        speeds = set(data.speeds[data.experiment_ids == experiment_id])
        if len(speeds) != 1:
            raise ValueError("A Thermal experiment cannot span operating-speed partitions")


def _training_counts(data: ThermalEmbeddingData) -> dict[str, object]:
    return {
        "experiments": len(set(data.experiment_ids)),
        "frames": len(data.labels),
        "per_speed": dict(sorted(Counter(data.speeds).items())),
        "per_class": dict(sorted(Counter(data.labels).items())),
        "train_frames": int(np.isin(data.speeds, TRAIN_SPEEDS).sum()),
        "validation_frames": int(np.isin(data.speeds, VALIDATION_SPEEDS).sum()),
        "test_frames": int(np.isin(data.speeds, TEST_SPEEDS).sum()),
        "missing_frames": data.audit["missing_frames"],
        "corrupt_frames": data.audit["corrupt_frames"],
    }


def _load_manifest(dataset_root: Path) -> dict[str, object]:
    path = dataset_root / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        manifest.get("persistent_id") != DATASET_DOI
        or manifest.get("dataset_version") != DATASET_VERSION
    ):
        raise ValueError("Thermal dataset manifest identity does not match the pinned dataset")
    return manifest
