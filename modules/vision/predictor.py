from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from modules.audio.evidence import bounded_evidence
from modules.vision.artifact import load_vision_artifact
from modules.vision.encoder import (
    FrozenResNet18Encoder,
    VisionFeatureEncoder,
    validate_encoder_metadata,
    validate_features,
)
from modules.vision.input import VisionInput
from modules.vision.preprocessing import resize_anomaly_map


@dataclass(frozen=True)
class VisionModelOutput:
    prediction: Prediction
    image_anomaly_score: float
    anomaly_map: NDArray[np.float64]


class VisionPredictor:
    def __init__(
        self,
        artifact_path: Path,
        encoder: VisionFeatureEncoder | None = None,
        encoder_path: Path = Path("models/pretrained/resnet18"),
        device: str = "cpu",
    ) -> None:
        self._artifact = load_vision_artifact(artifact_path)
        self._encoder = encoder or FrozenResNet18Encoder(
            encoder_path,
            device,
            self._artifact.metadata.encoder,
        )
        validate_encoder_metadata(self._encoder.metadata, self._artifact.metadata.encoder)

    @property
    def model_id(self) -> str:
        return "vision_visa_pcb1_v1"

    @property
    def supported_asset_types(self) -> tuple[str, ...]:
        return self._artifact.metadata.supported_asset_types

    @property
    def device(self) -> str:
        return self._encoder.device

    def predict(self, input_data: VisionInput) -> Prediction:
        return self.predict_with_localization(input_data).prediction

    def predict_with_localization(self, input_data: VisionInput) -> VisionModelOutput:
        features = self._encoder.encode_batch((input_data,))
        validate_features(features, 1, self._artifact.metadata.encoder)
        patch_map = self._artifact.detector.patch_scores(features.patch_embeddings)[0]
        anomaly_score = float(
            np.quantile(
                patch_map,
                self._artifact.detector.image_score_percentile,
                method="linear",
            )
        )
        threshold = self._artifact.metadata.image_threshold
        confidence = bounded_evidence(
            anomaly_score,
            threshold,
            np.asarray(self._artifact.normal_calibration_scores, dtype=np.float64),
        )
        prediction = Prediction(
            modality=Modality.VISION,
            label="visual_anomaly" if anomaly_score > threshold else "healthy",
            confidence=confidence,
        )
        canvas_size = int(self._artifact.metadata.encoder.preprocessing["canvas_size"])
        return VisionModelOutput(
            prediction=prediction,
            image_anomaly_score=anomaly_score,
            anomaly_map=resize_anomaly_map(patch_map, canvas_size),
        )
