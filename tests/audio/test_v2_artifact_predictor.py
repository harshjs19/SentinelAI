from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from domain.enums.modality import Modality
from modules.audio.artifact import (
    AUDIO_V2_ARTIFACT_FORMAT_VERSION,
    AudioV2ArtifactMetadata,
    AudioV2ModelArtifact,
    load_audio_artifact,
    save_audio_artifact,
)
from modules.audio.encoder import AudioEncoderMetadata
from modules.audio.input import AudioInput
from modules.audio.predictor import AudioPredictor


class FixedEmbeddingScoreDetector:
    def __init__(self, score: float) -> None:
        self.score = score

    def anomaly_scores(self, embeddings: np.ndarray) -> np.ndarray:
        return np.full(len(embeddings), self.score)


class FakeAudioEncoder:
    def __init__(self, metadata: AudioEncoderMetadata) -> None:
        self._metadata = metadata

    @property
    def metadata(self) -> AudioEncoderMetadata:
        return self._metadata

    @property
    def device(self) -> str:
        return "fake-cpu"

    def encode_batch(self, inputs: tuple[AudioInput, ...]) -> np.ndarray:
        return np.ones((len(inputs), self._metadata.dimension), dtype=np.float64)


def encoder_metadata() -> AudioEncoderMetadata:
    return AudioEncoderMetadata(
        model_id="fake/ast",
        revision="abc123",
        license="BSD-3-Clause",
        representation="mean-special-tokens",
        dimension=4,
        preprocessing_identity="fake-preprocessor-v1",
        preprocessing_config={"sampling_rate": 16_000},
    )


def metadata() -> AudioV2ArtifactMetadata:
    return AudioV2ArtifactMetadata(
        format_version=AUDIO_V2_ARTIFACT_FORMAT_VERSION,
        dataset_source="https://example.test",
        dataset_doi="test",
        dataset_license="CC BY 4.0",
        dataset_archive="bearing.zip",
        dataset_checksum="md5:test",
        machine_subset="bearing",
        supported_asset_types=("bearing",),
        audio_sample_rate=16_000,
        audio_channels=1,
        clip_duration_seconds=10.0,
        encoder=encoder_metadata(),
        selected_detector="fixed",
        model_parameters={},
        training_sections=("00", "01"),
        validation_section="01",
        benchmark_section="02",
        selection_metric="test",
        threshold_policy="normal p99",
        threshold_percentile=0.99,
        threshold=0.5,
        calibration_count=5,
        calibration_score_summary={},
        validation_metrics={},
        benchmark_metrics={},
    )


def save_v2_artifact(path: Path, score: float) -> None:
    save_audio_artifact(
        AudioV2ModelArtifact(
            detector=FixedEmbeddingScoreDetector(score),
            normal_calibration_scores=(0.0, 0.25, 0.5, 0.75, 1.0),
            metadata=metadata(),
        ),
        path,
    )


def test_v2_artifact_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "audio-v2.joblib"
    save_v2_artifact(path, 0.2)

    artifact = load_audio_artifact(path)

    assert isinstance(artifact, AudioV2ModelArtifact)
    assert artifact.metadata.format_version == 2
    assert artifact.metadata.encoder.revision == "abc123"


@pytest.mark.parametrize(
    ("score", "expected_label"),
    [(0.2, "healthy"), (0.8, "acoustic_anomaly")],
)
def test_v2_predictor_returns_bounded_audio_prediction(
    tmp_path: Path,
    score: float,
    expected_label: str,
) -> None:
    path = tmp_path / "audio-v2.joblib"
    save_v2_artifact(path, score)
    predictor = AudioPredictor(path, encoder=FakeAudioEncoder(encoder_metadata()))

    prediction = predictor.predict(AudioInput(np.ones(1_600, dtype=np.float32), 16_000))

    assert prediction.modality is Modality.AUDIO
    assert prediction.label == expected_label
    assert 0 <= prediction.confidence <= 1


def test_v2_predictor_rejects_encoder_metadata_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "audio-v2.joblib"
    save_v2_artifact(path, 0.2)
    mismatched = replace(encoder_metadata(), revision="different")

    with pytest.raises(ValueError, match="revision"):
        AudioPredictor(path, encoder=FakeAudioEncoder(mismatched))


def test_v2_predictor_keeps_missing_local_encoder_explicit(tmp_path: Path) -> None:
    path = tmp_path / "audio-v2.joblib"
    save_v2_artifact(path, 0.2)

    with pytest.raises(FileNotFoundError, match="encoder identity"):
        AudioPredictor(path, encoder_path=tmp_path / "missing-encoder")
