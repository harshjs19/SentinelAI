from pathlib import Path

import numpy as np

from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from modules.thermal.artifact import load_thermal_artifact
from modules.thermal.config import CONDITION_LABELS
from modules.thermal.encoder import (
    FrozenThermalResNet18Encoder,
    ThermalFeatureEncoder,
    validate_embeddings,
    validate_thermal_encoder_metadata,
)
from modules.thermal.evaluation import aligned_probabilities
from modules.thermal.input import ThermalInput


class ThermalPredictor:
    def __init__(
        self,
        artifact_path: Path,
        encoder: ThermalFeatureEncoder | None = None,
        encoder_path: Path = Path("models/pretrained/resnet18"),
        device: str = "cpu",
    ) -> None:
        self._artifact = load_thermal_artifact(artifact_path)
        self._encoder = encoder or FrozenThermalResNet18Encoder(
            encoder_path,
            device,
            self._artifact.metadata.encoder,
        )
        validate_thermal_encoder_metadata(
            self._encoder.metadata,
            self._artifact.metadata.encoder,
        )

    @property
    def model_id(self) -> str:
        return "thermal_cora_v1"

    @property
    def supported_asset_types(self) -> tuple[str, ...]:
        return self._artifact.metadata.supported_asset_types

    @property
    def device(self) -> str:
        return self._encoder.device

    def predict(self, input_data: ThermalInput) -> Prediction:
        embeddings = self._encoder.encode_batch((input_data,))
        validate_embeddings(embeddings, 1, self._artifact.metadata.embedding_dimension)
        labels = tuple(CONDITION_LABELS.values())
        probabilities = aligned_probabilities(self._artifact.pipeline, embeddings, labels)[0]
        selected = int(np.argmax(probabilities))
        return Prediction(
            modality=Modality.THERMAL,
            label=labels[selected],
            confidence=float(probabilities[selected]),
        )
