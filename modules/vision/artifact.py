from dataclasses import asdict, dataclass
from pathlib import Path

import joblib

from modules.vision.encoder import VisionEncoderMetadata
from modules.vision.modeling import PatchNearestNeighborDetector

VISION_ARTIFACT_FORMAT_VERSION = 1


@dataclass(frozen=True)
class VisionArtifactMetadata:
    format_version: int
    dataset: str
    dataset_source: str
    dataset_license: str
    dataset_archive_sha256: str
    subset: str
    supported_asset_types: tuple[str, ...]
    official_split_identity: dict[str, object]
    detector_fit_normal_count: int
    calibration_normal_count: int
    test_normal_count: int
    test_anomaly_count: int
    encoder: VisionEncoderMetadata
    patch_normalization: str
    patch_bank_sampling: dict[str, object]
    patch_bank_size: int
    distance_metric: str
    image_score_rule: str
    image_threshold_policy: str
    image_threshold_percentile: float
    image_threshold: float
    pixel_threshold_policy: str
    pixel_threshold_percentile: float
    pixel_threshold: float
    calibration_score_summary: dict[str, float]
    global_evaluation_metrics: dict[str, object]
    patch_evaluation_metrics: dict[str, object]
    localization_metrics: dict[str, float]
    confidence_semantics: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class VisionModelArtifact:
    detector: PatchNearestNeighborDetector
    normal_calibration_scores: tuple[float, ...]
    metadata: VisionArtifactMetadata


def save_vision_artifact(artifact: VisionModelArtifact, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, path)


def load_vision_artifact(path: Path) -> VisionModelArtifact:
    artifact = joblib.load(path)
    if not isinstance(artifact, VisionModelArtifact):
        raise ValueError(f"Unsupported Vision artifact: {path}")
    if artifact.metadata.format_version != VISION_ARTIFACT_FORMAT_VERSION:
        raise ValueError(f"Unsupported Vision artifact format: {artifact.metadata.format_version}")
    if not artifact.normal_calibration_scores:
        raise ValueError("Vision artifact has no normal calibration scores")
    if artifact.detector.bank_size != artifact.metadata.patch_bank_size:
        raise ValueError("Vision artifact patch memory does not match its metadata")
    return artifact
