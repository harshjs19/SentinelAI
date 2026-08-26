from dataclasses import dataclass

from ai_core.model_provenance import ProducingModelContext
from domain.entities.prediction import Prediction


@dataclass(frozen=True)
class InferenceResult:
    prediction: Prediction
    producing_model: ProducingModelContext

    def __post_init__(self) -> None:
        if self.prediction.modality is not self.producing_model.modality:
            raise ValueError(
                "Inference result Prediction and producing-model modalities must match"
            )
