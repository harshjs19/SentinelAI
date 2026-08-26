from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from modules.timeseries.artifact import load_artifact


class TimeseriesPredictor:
    def __init__(self, artifact_path: Path) -> None:
        self._artifact = load_artifact(artifact_path)

    @property
    def model_id(self) -> str:
        return "timeseries_utk_v1"

    def predict_probabilities(self, features: Mapping[str, float]) -> dict[str, float]:
        expected = set(self._artifact.metadata.feature_names)
        missing = expected - set(features)
        if missing:
            raise ValueError(f"Missing model features: {', '.join(sorted(missing))}")

        frame = pd.DataFrame(
            [[features[name] for name in self._artifact.metadata.feature_names]],
            columns=self._artifact.metadata.feature_names,
        )
        probabilities = self._artifact.pipeline.predict_proba(frame)[0]
        classes = self._artifact.pipeline.classes_
        return {
            str(label): float(probability) for label, probability in zip(classes, probabilities)
        }

    def predict(self, input_data: Mapping[str, float]) -> Prediction:
        probabilities = self.predict_probabilities(input_data)
        label, confidence = max(probabilities.items(), key=lambda item: item[1])
        return Prediction(
            modality=Modality.TIMESERIES,
            label=label,
            confidence=confidence,
        )
