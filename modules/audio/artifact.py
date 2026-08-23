from dataclasses import asdict, dataclass
from pathlib import Path

import joblib

from modules.audio.modeling import AudioDetector

AUDIO_ARTIFACT_FORMAT_VERSION = 1


@dataclass(frozen=True)
class AudioArtifactMetadata:
    format_version: int
    dataset_source: str
    dataset_doi: str
    dataset_license: str
    dataset_archive: str
    dataset_checksum: str
    machine_subset: str
    supported_asset_types: tuple[str, ...]
    audio_sample_rate: int
    audio_channels: int
    clip_duration_seconds: float
    feature_config: dict[str, object]
    feature_names: tuple[str, ...]
    selected_detector: str
    model_parameters: dict[str, object]
    training_sections: tuple[str, ...]
    validation_section: str
    test_section: str
    selection_metric: str
    threshold_policy: str
    threshold_percentile: float
    threshold: float
    calibration_count: int
    calibration_score_summary: dict[str, float]
    validation_metrics: dict[str, object]
    test_metrics: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class AudioModelArtifact:
    detector: AudioDetector
    normal_calibration_scores: tuple[float, ...]
    metadata: AudioArtifactMetadata


def save_audio_artifact(artifact: AudioModelArtifact, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, path)


def load_audio_artifact(path: Path) -> AudioModelArtifact:
    artifact = joblib.load(path)
    if not isinstance(artifact, AudioModelArtifact):
        raise ValueError(f"Unsupported audio artifact: {path}")
    if artifact.metadata.format_version != AUDIO_ARTIFACT_FORMAT_VERSION:
        raise ValueError(f"Unsupported audio artifact format: {artifact.metadata.format_version}")
    if not artifact.normal_calibration_scores:
        raise ValueError("Audio artifact has no normal calibration scores")
    return artifact
