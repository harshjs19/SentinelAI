from pathlib import Path

import numpy as np

from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from modules.audio.artifact import load_audio_artifact
from modules.audio.config import AudioFeatureConfig
from modules.audio.evidence import bounded_evidence
from modules.audio.features import extract_audio_features
from modules.audio.input import AudioInput


class AudioPredictor:
    def __init__(self, artifact_path: Path) -> None:
        self._artifact = load_audio_artifact(artifact_path)
        config = self._artifact.metadata.feature_config
        self._feature_config = AudioFeatureConfig(
            sample_rate=int(config["sample_rate"]),
            n_mels=int(config["n_mels"]),
            n_fft=int(config["n_fft"]),
            hop_length=int(config["hop_length"]),
            fmin=float(config["fmin"]),
            fmax=float(config["fmax"]),
        )

    @property
    def supported_asset_types(self) -> tuple[str, ...]:
        return self._artifact.metadata.supported_asset_types

    def predict(self, input_data: AudioInput) -> Prediction:
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
