from pathlib import Path

import numpy as np

from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from modules.audio.artifact import AudioModelArtifact, AudioV2ModelArtifact, load_audio_artifact
from modules.audio.config import AudioFeatureConfig
from modules.audio.encoder import (
    AudioEmbeddingEncoder,
    FrozenASTEncoder,
    validate_embedding_matrix,
    validate_encoder_metadata,
)
from modules.audio.evidence import bounded_evidence
from modules.audio.features import extract_audio_features
from modules.audio.input import AudioInput


class AudioPredictor:
    def __init__(
        self,
        artifact_path: Path,
        encoder: AudioEmbeddingEncoder | None = None,
        encoder_path: Path = Path("models/pretrained/ast-audioset"),
        device: str = "cpu",
    ) -> None:
        self._artifact = load_audio_artifact(artifact_path)
        self._feature_config: AudioFeatureConfig | None = None
        self._encoder: AudioEmbeddingEncoder | None = None
        if isinstance(self._artifact, AudioModelArtifact):
            config = self._artifact.metadata.feature_config
            self._feature_config = AudioFeatureConfig(
                sample_rate=int(config["sample_rate"]),
                n_mels=int(config["n_mels"]),
                n_fft=int(config["n_fft"]),
                hop_length=int(config["hop_length"]),
                fmin=float(config["fmin"]),
                fmax=float(config["fmax"]),
            )
        else:
            self._encoder = encoder or FrozenASTEncoder(
                encoder_path,
                device,
                self._artifact.metadata.encoder,
            )
            validate_encoder_metadata(
                self._encoder.metadata,
                self._artifact.metadata.encoder,
            )

    @property
    def supported_asset_types(self) -> tuple[str, ...]:
        return self._artifact.metadata.supported_asset_types

    def predict(self, input_data: AudioInput) -> Prediction:
        if isinstance(self._artifact, AudioV2ModelArtifact):
            if self._encoder is None:  # pragma: no cover - constructor invariant
                raise RuntimeError("Audio V2 encoder is unavailable")
            features = self._encoder.encode_batch((input_data,))
            validate_embedding_matrix(
                features,
                expected_rows=1,
                expected_dimension=self._artifact.metadata.encoder.dimension,
            )
        else:
            if self._feature_config is None:  # pragma: no cover - constructor invariant
                raise RuntimeError("Audio V1 feature configuration is unavailable")
            features = extract_audio_features(input_data, self._feature_config).reshape(1, -1)
        anomaly_score = float(self._artifact.detector.anomaly_scores(features)[0])
        threshold = self._artifact.metadata.threshold
        is_anomaly = anomaly_score > threshold
        confidence = bounded_evidence(
            anomaly_score,
            threshold,
            np.asarray(self._artifact.normal_calibration_scores, dtype=np.float64),
        )
        return Prediction(
            modality=Modality.AUDIO,
            label="acoustic_anomaly" if is_anomaly else "healthy",
            confidence=confidence,
        )
