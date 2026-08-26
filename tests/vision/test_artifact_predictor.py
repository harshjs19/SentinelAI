from dataclasses import replace
from pathlib import Path

import joblib
import numpy as np
import pytest

from domain.enums.modality import Modality
from modules.vision.artifact import (
    VISION_ARTIFACT_FORMAT_VERSION,
    VisionArtifactMetadata,
    VisionModelArtifact,
    load_vision_artifact,
    save_vision_artifact,
)
from modules.vision.encoder import VisionEncoderMetadata, VisionFeatures
from modules.vision.input import VisionInput
from modules.vision.modeling import PatchNearestNeighborDetector
from modules.vision.predictor import VisionPredictor


def encoder_metadata() -> VisionEncoderMetadata:
    return VisionEncoderMetadata(
        model_id="fake-resnet18",
        weights_id="fake-v1",
        weights_filename="fake.pth",
        weights_sha256="abc",
        weights_bytes=1,
        torchvision_version="test",
        global_layer="layer4",
        global_dimension=2,
        patch_layers=("layer2", "layer3"),
        patch_dimension=2,
        patch_grid=(2, 2),
        preprocessing={"canvas_size": 8},
    )


def metadata(bank_size: int) -> VisionArtifactMetadata:
    return VisionArtifactMetadata(
        format_version=VISION_ARTIFACT_FORMAT_VERSION,
        dataset="VisA",
        dataset_source="official",
        dataset_license="CC BY 4.0",
        dataset_archive_sha256="sha",
        subset="PCB1",
        supported_asset_types=("pcb1",),
        official_split_identity={"name": "1cls.csv"},
        detector_fit_normal_count=3,
        calibration_normal_count=3,
        test_normal_count=1,
        test_anomaly_count=1,
        encoder=encoder_metadata(),
        patch_normalization="l2",
        patch_bank_sampling={"policy": "seeded_uniform", "seed": 42, "maximum": 4},
        patch_bank_size=bank_size,
        distance_metric="cosine_distance",
        image_score_rule="p99_patch_distance",
        image_threshold_policy="p99_normal_calibration_image_scores",
        image_threshold_percentile=0.99,
        image_threshold=0.2,
        pixel_threshold_policy="p99.9_normal_calibration_pixels",
        pixel_threshold_percentile=0.999,
        pixel_threshold=0.3,
        calibration_score_summary={"minimum": 0.0, "maximum": 0.2},
        global_evaluation_metrics={},
        patch_evaluation_metrics={},
        localization_metrics={},
        confidence_semantics="bounded raw evidence",
    )


def artifact() -> VisionModelArtifact:
    normal = np.zeros((1, 2, 2, 2), dtype=np.float64)
    normal[..., 0] = 1.0
    detector = PatchNearestNeighborDetector(max_bank_size=4).fit(normal)
    return VisionModelArtifact(detector, (0.0, 0.1, 0.2), metadata(detector.bank_size))


class FakeEncoder:
    metadata = encoder_metadata()
    device = "cpu"

    def encode_batch(self, inputs: tuple[VisionInput, ...]) -> VisionFeatures:
        rows = len(inputs)
        global_embeddings = np.zeros((rows, 2), dtype=np.float64)
        patches = np.zeros((rows, 2, 2, 2), dtype=np.float64)
        for index, image in enumerate(inputs):
            channel = 1 if float(image.pixels.mean()) > 127 else 0
            global_embeddings[index, channel] = 1.0
            patches[index, ..., channel] = 1.0
        return VisionFeatures(global_embeddings, patches)


def test_artifact_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "vision.joblib"
    save_vision_artifact(artifact(), path)

    loaded = load_vision_artifact(path)

    assert loaded.metadata.subset == "PCB1"
    assert loaded.detector.bank_size == 4


def test_rejects_unsupported_artifact_version(tmp_path: Path) -> None:
    invalid = artifact()
    invalid.metadata = replace(invalid.metadata, format_version=999)
    path = tmp_path / "vision.joblib"
    joblib.dump(invalid, path)

    with pytest.raises(ValueError, match="format"):
        load_vision_artifact(path)


@pytest.mark.parametrize(
    ("pixel_value", "expected_label"),
    [(0, "healthy"), (255, "visual_anomaly")],
)
def test_predictor_returns_bounded_vision_prediction(
    tmp_path: Path,
    pixel_value: int,
    expected_label: str,
) -> None:
    path = tmp_path / "vision.joblib"
    save_vision_artifact(artifact(), path)
    predictor = VisionPredictor(path, encoder=FakeEncoder())
    image = VisionInput(np.full((4, 4, 3), pixel_value, dtype=np.uint8))

    output = predictor.predict_with_localization(image)

    assert predictor.model_id == "vision_visa_pcb1_v1"
    assert output.prediction.modality is Modality.VISION
    assert output.prediction.label == expected_label
    assert 0 <= output.prediction.confidence <= 1
    assert output.anomaly_map.shape == (8, 8)
    assert output.prediction.label not in {"scratch", "crack", "missing_component"}


def test_rejects_encoder_identity_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "vision.joblib"
    save_vision_artifact(artifact(), path)

    class WrongEncoder(FakeEncoder):
        metadata = replace(encoder_metadata(), weights_id="wrong")

    with pytest.raises(ValueError, match="weights identity"):
        VisionPredictor(path, encoder=WrongEncoder())
