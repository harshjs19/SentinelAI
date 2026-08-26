from dataclasses import replace
from pathlib import Path

import joblib
import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from domain.enums.modality import Modality
from modules.thermal.artifact import (
    THERMAL_ARTIFACT_FORMAT_VERSION,
    ThermalArtifactMetadata,
    ThermalModelArtifact,
    load_thermal_artifact,
    save_thermal_artifact,
)
from modules.thermal.config import CONDITION_LABELS, SPEED_RPM, SUPPORTED_ASSET_TYPES
from modules.thermal.input import ThermalInput
from modules.thermal.predictor import ThermalPredictor
from modules.vision.encoder import VisionEncoderMetadata

LABELS = tuple(CONDITION_LABELS.values())


def encoder_metadata() -> VisionEncoderMetadata:
    return VisionEncoderMetadata(
        model_id="fake-resnet18",
        weights_id="fake-imagenet-v1",
        weights_filename="fake.pth",
        weights_sha256="abc",
        weights_bytes=1,
        torchvision_version="test",
        global_layer="layer4_adaptive_average_pool",
        global_dimension=512,
        patch_layers=("layer2", "layer3"),
        patch_dimension=384,
        patch_grid=(16, 16),
        preprocessing={"canvas_size": 256},
        classification_logits_used=False,
    )


def fitted_pipeline() -> Pipeline:
    features: list[np.ndarray] = []
    labels: list[str] = []
    for index, label in enumerate(LABELS):
        for _ in range(4):
            row = np.zeros(512, dtype=np.float64)
            row[index] = 10.0
            features.append(row)
            labels.append(label)
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("classifier", LogisticRegression(max_iter=1_000, random_state=42)),
        ]
    ).fit(np.stack(features), np.asarray(labels))


def artifact_metadata() -> ThermalArtifactMetadata:
    return ThermalArtifactMetadata(
        format_version=THERMAL_ARTIFACT_FORMAT_VERSION,
        dataset_doi="doi:10.34810/DATA2500",
        dataset_version="2.1",
        dataset_license="CC BY 4.0",
        dataset_files=(),
        data_representation="uint8 RGB appearance",
        condition_mapping=CONDITION_LABELS,
        speed_rpm_mapping=SPEED_RPM,
        split={"train": ["F5", "F15"], "validation": ["F50"], "test": ["F60"]},
        supported_asset_types=SUPPORTED_ASSET_TYPES,
        preprocessing={"canvas_size": 256},
        encoder=encoder_metadata(),
        embedding_dimension=512,
        candidate_parameters={},
        validation_metrics={},
        selection_metric="macro_f1",
        selected_model="logistic_regression",
        final_fit_speeds=("F5", "F15", "F50"),
        locked_test_speed="F60",
        final_test_metrics={},
        experiment_test_metrics={},
        training_counts={},
        confidence_semantics="raw predict_proba",
    )


def artifact() -> ThermalModelArtifact:
    return ThermalModelArtifact(fitted_pipeline(), artifact_metadata())


class FakeEncoder:
    metadata = encoder_metadata()
    device = "cpu"

    def encode_batch(self, inputs: tuple[ThermalInput, ...]) -> np.ndarray:
        result = np.zeros((len(inputs), 512), dtype=np.float64)
        for row, image in enumerate(inputs):
            index = min(len(LABELS) - 1, int(image.pixels[0, 0, 0]))
            result[row, index] = 10.0
        return result


def test_artifact_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "thermal.joblib"
    save_thermal_artifact(artifact(), path)

    loaded = load_thermal_artifact(path)

    assert loaded.metadata.format_version == THERMAL_ARTIFACT_FORMAT_VERSION
    assert set(loaded.pipeline.classes_) == set(LABELS)
    assert loaded.metadata.final_fit_speeds == ("F5", "F15", "F50")


def test_rejects_unsupported_artifact_version(tmp_path: Path) -> None:
    invalid = artifact()
    invalid.metadata = replace(invalid.metadata, format_version=999)
    path = tmp_path / "thermal.joblib"
    joblib.dump(invalid, path)

    with pytest.raises(ValueError, match="format"):
        load_thermal_artifact(path)


@pytest.mark.parametrize(
    ("class_index", "expected_label"),
    [(0, "healthy"), (1, "bearing_fault"), (8, "gear_wear_75")],
)
def test_predictor_returns_canonical_thermal_prediction(
    tmp_path: Path,
    class_index: int,
    expected_label: str,
) -> None:
    path = tmp_path / "thermal.joblib"
    save_thermal_artifact(artifact(), path)
    predictor = ThermalPredictor(path, encoder=FakeEncoder())
    image = ThermalInput(np.full((4, 4, 3), class_index, dtype=np.uint8))

    prediction = predictor.predict(image)

    assert predictor.model_id == "thermal_cora_v1"
    assert prediction.modality is Modality.THERMAL
    assert prediction.label == expected_label
    assert 0 <= prediction.confidence <= 1


def test_rejects_encoder_identity_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "thermal.joblib"
    save_thermal_artifact(artifact(), path)

    class WrongEncoder(FakeEncoder):
        metadata = replace(encoder_metadata(), weights_id="wrong")

    with pytest.raises(ValueError, match="weights identity"):
        ThermalPredictor(path, encoder=WrongEncoder())
