from pathlib import Path

import numpy as np
import pytest

from domain.enums.modality import Modality
from modules.audio.artifact import (
    AUDIO_ARTIFACT_FORMAT_VERSION,
    AudioArtifactMetadata,
    AudioModelArtifact,
    load_audio_artifact,
    save_audio_artifact,
)
from modules.audio.config import AudioFeatureConfig
from modules.audio.features import feature_config_metadata, feature_names
from modules.audio.input import AudioInput
from modules.audio.predictor import AudioPredictor


class FixedScoreDetector:
    def __init__(self, score: float) -> None:
        self.score = score

    def anomaly_scores(self, features: np.ndarray) -> np.ndarray:
        return np.full(len(features), self.score)


def metadata(format_version: int = AUDIO_ARTIFACT_FORMAT_VERSION) -> AudioArtifactMetadata:
    feature = AudioFeatureConfig(n_mels=4, n_fft=256, hop_length=128)
    return AudioArtifactMetadata(
        format_version=format_version,
        dataset_source="https://zenodo.org/records/6529888",
        dataset_doi="10.5281/zenodo.6529888",
        dataset_license="CC BY 4.0",
        dataset_archive="bearing.zip",
        dataset_checksum="md5:test",
        machine_subset="bearing",
        supported_asset_types=("bearing",),
        audio_sample_rate=16_000,
        audio_channels=1,
        clip_duration_seconds=10.0,
        feature_config=feature_config_metadata(feature),
        feature_names=feature_names(feature),
        selected_detector="fixed",
        model_parameters={},
        training_sections=("00", "01"),
        validation_section="01",
        test_section="02",
        selection_metric="test",
        threshold_policy="test",
        threshold_percentile=0.99,
        threshold=0.5,
        calibration_count=5,
        calibration_score_summary={},
        validation_metrics={},
        test_metrics={},
    )


def save_fixed_artifact(path: Path, score: float, format_version: int = 1) -> None:
    save_audio_artifact(
        AudioModelArtifact(
            detector=FixedScoreDetector(score),
            normal_calibration_scores=(0.0, 0.25, 0.5, 0.75, 1.0),
            metadata=metadata(format_version),
        ),
        path,
    )


def test_artifact_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "audio.joblib"
    save_fixed_artifact(path, 0.2)

    artifact = load_audio_artifact(path)

    assert artifact.metadata.machine_subset == "bearing"
    assert artifact.metadata.supported_asset_types == ("bearing",)
    assert artifact.normal_calibration_scores == (0.0, 0.25, 0.5, 0.75, 1.0)


def test_rejects_unsupported_artifact_version(tmp_path: Path) -> None:
    path = tmp_path / "audio.joblib"
    save_fixed_artifact(path, 0.2, format_version=99)

    with pytest.raises(ValueError, match="format: 99"):
        load_audio_artifact(path)


@pytest.mark.parametrize(
    ("score", "expected_label"),
    [(0.2, "healthy"), (0.8, "acoustic_anomaly")],
)
def test_predictor_returns_bounded_audio_prediction(
    tmp_path: Path,
    score: float,
    expected_label: str,
) -> None:
    path = tmp_path / "audio.joblib"
    save_fixed_artifact(path, score)
    waveform = np.sin(np.linspace(0, 100, 16_000)).astype(np.float32)

    predictor = AudioPredictor(path)
    prediction = predictor.predict(AudioInput(waveform, 16_000))

    assert predictor.model_id == "audio_mimii_v1"
    assert prediction.modality is Modality.AUDIO
    assert prediction.label == expected_label
    assert 0 <= prediction.confidence <= 1
