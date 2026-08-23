from typing import Protocol, TypeVar

from domain.entities.prediction import Prediction

InputT = TypeVar("InputT", contravariant=True)


class Predictor(Protocol[InputT]):
    def predict(self, input_data: InputT) -> Prediction: ...
