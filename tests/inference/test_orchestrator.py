from uuid import uuid4

import numpy as np
import pytest

from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from inference.event_bus import EventBus
from inference.events import PredictionProduced
from inference.orchestrator import (
    InferenceOrchestrator,
    PredictionModalityMismatchError,
    PredictorInputTypeError,
    PredictorNotRegisteredError,
)
from modules.audio.input import AudioInput


class FakePredictor:
    def __init__(self, prediction: Prediction) -> None:
        self.prediction = prediction
        self.inputs: list[object] = []

    def predict(self, input_data: object) -> Prediction:
        self.inputs.append(input_data)
        return self.prediction


@pytest.mark.asyncio
async def test_invokes_predictor_returns_prediction_and_publishes_event() -> None:
    bus = EventBus()
    orchestrator = InferenceOrchestrator(bus)
    prediction = Prediction(Modality.TIMESERIES, "healthy", 0.82)
    predictor = FakePredictor(prediction)
    orchestrator.register(Modality.TIMESERIES, predictor, input_type=dict)
    events: list[PredictionProduced] = []

    async def record(event: PredictionProduced) -> None:
        events.append(event)

    bus.subscribe(PredictionProduced, record)
    machine_id = uuid4()
    input_data = {"feature": 1.0}

    result = await orchestrator.predict(machine_id, Modality.TIMESERIES, input_data)

    assert result == prediction
    assert predictor.inputs == [input_data]
    assert events == [PredictionProduced(machine_id=machine_id, prediction=prediction)]


@pytest.mark.asyncio
async def test_unknown_modality_raises_clear_error() -> None:
    orchestrator = InferenceOrchestrator(EventBus())

    with pytest.raises(PredictorNotRegisteredError, match="audio"):
        await orchestrator.predict(uuid4(), Modality.AUDIO, b"audio")


@pytest.mark.asyncio
async def test_wrong_prediction_modality_is_rejected() -> None:
    orchestrator = InferenceOrchestrator(EventBus())
    predictor = FakePredictor(Prediction(Modality.AUDIO, "bearing_fault", 0.9))
    orchestrator.register(Modality.TIMESERIES, predictor, input_type=dict)

    with pytest.raises(PredictionModalityMismatchError, match="returned audio"):
        await orchestrator.predict(uuid4(), Modality.TIMESERIES, {})


@pytest.mark.asyncio
async def test_wrong_input_type_is_rejected() -> None:
    orchestrator = InferenceOrchestrator(EventBus())
    predictor = FakePredictor(Prediction(Modality.TIMESERIES, "healthy", 0.8))
    orchestrator.register(Modality.TIMESERIES, predictor, input_type=dict)

    with pytest.raises(PredictorInputTypeError, match="requires dict"):
        await orchestrator.predict(uuid4(), Modality.TIMESERIES, [1.0])


@pytest.mark.asyncio
async def test_invokes_audio_predictor_with_distinct_input_type() -> None:
    orchestrator = InferenceOrchestrator(EventBus())
    prediction = Prediction(Modality.AUDIO, "acoustic_anomaly", 0.73)
    predictor = FakePredictor(prediction)
    orchestrator.register(Modality.AUDIO, predictor, input_type=AudioInput)
    audio = AudioInput(np.zeros(1_600, dtype=np.float32), 16_000)

    result = await orchestrator.predict(uuid4(), Modality.AUDIO, audio)

    assert result is prediction
    assert predictor.inputs == [audio]
