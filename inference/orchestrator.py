from typing import Any
from uuid import UUID

from ai_core.model_provenance import ProducingModelContext
from ai_core.predictor import Predictor
from domain.enums.modality import Modality
from inference.event_bus import EventBus
from inference.events import PredictionProduced
from inference.result import InferenceResult


class PredictorNotRegisteredError(RuntimeError):
    pass


class PredictionModalityMismatchError(RuntimeError):
    pass


class PredictorInputTypeError(TypeError):
    pass


class ProducingModelModalityMismatchError(RuntimeError):
    pass


class InferenceOrchestrator:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._predictors: dict[
            Modality,
            tuple[type[object], Predictor[Any], ProducingModelContext],
        ] = {}

    def register(
        self,
        modality: Modality,
        predictor: Predictor[Any],
        *,
        input_type: type[object],
        producing_model: ProducingModelContext,
    ) -> None:
        if producing_model.modality is not modality:
            raise ProducingModelModalityMismatchError(
                f"Predictor registered for {modality.value} has "
                f"{producing_model.modality.value} producing-model context"
            )
        self._predictors[modality] = (input_type, predictor, producing_model)

    async def predict(
        self,
        machine_id: UUID,
        modality: Modality,
        input_data: object,
    ) -> InferenceResult:
        try:
            input_type, predictor, producing_model = self._predictors[modality]
        except KeyError as error:
            raise PredictorNotRegisteredError(
                f"No predictor registered for modality: {modality.value}"
            ) from error

        if not isinstance(input_data, input_type):
            raise PredictorInputTypeError(
                f"Predictor for {modality.value} requires {input_type.__name__} input"
            )

        prediction = predictor.predict(input_data)
        if prediction.modality is not modality:
            raise PredictionModalityMismatchError(
                f"Predictor registered for {modality.value} returned {prediction.modality.value}"
            )

        await self._event_bus.publish(
            PredictionProduced(machine_id=machine_id, prediction=prediction)
        )
        return InferenceResult(
            prediction=prediction,
            producing_model=producing_model,
        )
