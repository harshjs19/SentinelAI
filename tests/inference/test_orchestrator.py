from uuid import uuid4

import numpy as np
import pytest

from ai_core.model_capabilities import get_runtime_default_capability
from ai_core.model_provenance import (
    ProducingModelContext,
    snapshot_producing_model_context,
)
from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from inference.event_bus import EventBus
from inference.events import PredictionProduced
from inference.orchestrator import (
    InferenceOrchestrator,
    PredictionModalityMismatchError,
    PredictorInputTypeError,
    PredictorNotRegisteredError,
    ProducingModelModalityMismatchError,
)
from modules.audio.input import AudioInput
from modules.thermal.input import ThermalInput
from modules.vision.input import VisionInput


class FakePredictor:
    def __init__(self, prediction: Prediction) -> None:
        self.prediction = prediction
        self.inputs: list[object] = []

    def predict(self, input_data: object) -> Prediction:
        self.inputs.append(input_data)
        return self.prediction


def producing_model(modality: Modality) -> ProducingModelContext:
    return snapshot_producing_model_context(get_runtime_default_capability(modality))


@pytest.mark.asyncio
async def test_invokes_predictor_returns_prediction_and_publishes_event() -> None:
    bus = EventBus()
    orchestrator = InferenceOrchestrator(bus)
    prediction = Prediction(Modality.TIMESERIES, "healthy", 0.82)
    predictor = FakePredictor(prediction)
    model_context = producing_model(Modality.TIMESERIES)
    orchestrator.register(
        Modality.TIMESERIES,
        predictor,
        input_type=dict,
        producing_model=model_context,
    )
    events: list[PredictionProduced] = []

    async def record(event: PredictionProduced) -> None:
        events.append(event)

    bus.subscribe(PredictionProduced, record)
    machine_id = uuid4()
    input_data = {"feature": 1.0}

    result = await orchestrator.predict(machine_id, Modality.TIMESERIES, input_data)

    assert result.prediction == prediction
    assert result.producing_model == model_context
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
    orchestrator.register(
        Modality.TIMESERIES,
        predictor,
        input_type=dict,
        producing_model=producing_model(Modality.TIMESERIES),
    )

    with pytest.raises(PredictionModalityMismatchError, match="returned audio"):
        await orchestrator.predict(uuid4(), Modality.TIMESERIES, {})


@pytest.mark.asyncio
async def test_wrong_input_type_is_rejected() -> None:
    orchestrator = InferenceOrchestrator(EventBus())
    predictor = FakePredictor(Prediction(Modality.TIMESERIES, "healthy", 0.8))
    orchestrator.register(
        Modality.TIMESERIES,
        predictor,
        input_type=dict,
        producing_model=producing_model(Modality.TIMESERIES),
    )

    with pytest.raises(PredictorInputTypeError, match="requires dict"):
        await orchestrator.predict(uuid4(), Modality.TIMESERIES, [1.0])


@pytest.mark.asyncio
async def test_invokes_audio_predictor_with_distinct_input_type() -> None:
    orchestrator = InferenceOrchestrator(EventBus())
    prediction = Prediction(Modality.AUDIO, "acoustic_anomaly", 0.73)
    predictor = FakePredictor(prediction)
    orchestrator.register(
        Modality.AUDIO,
        predictor,
        input_type=AudioInput,
        producing_model=producing_model(Modality.AUDIO),
    )
    audio = AudioInput(np.zeros(1_600, dtype=np.float32), 16_000)

    result = await orchestrator.predict(uuid4(), Modality.AUDIO, audio)

    assert result.prediction is prediction
    assert result.producing_model.model_id == "audio_mimii_v1"
    assert predictor.inputs == [audio]


@pytest.mark.asyncio
async def test_invokes_vision_predictor_with_distinct_input_type() -> None:
    orchestrator = InferenceOrchestrator(EventBus())
    prediction = Prediction(Modality.VISION, "visual_anomaly", 0.79)
    predictor = FakePredictor(prediction)
    orchestrator.register(
        Modality.VISION,
        predictor,
        input_type=VisionInput,
        producing_model=producing_model(Modality.VISION),
    )
    image = VisionInput(np.zeros((8, 8, 3), dtype=np.uint8))

    result = await orchestrator.predict(uuid4(), Modality.VISION, image)

    assert result.prediction is prediction
    assert result.producing_model.model_id == "vision_visa_pcb1_v1"
    assert predictor.inputs == [image]


@pytest.mark.asyncio
async def test_invokes_thermal_predictor_with_distinct_input_type() -> None:
    orchestrator = InferenceOrchestrator(EventBus())
    prediction = Prediction(Modality.THERMAL, "bearing_fault", 0.74)
    predictor = FakePredictor(prediction)
    orchestrator.register(
        Modality.THERMAL,
        predictor,
        input_type=ThermalInput,
        producing_model=producing_model(Modality.THERMAL),
    )
    thermogram = ThermalInput(np.zeros((8, 8, 3), dtype=np.uint8))

    result = await orchestrator.predict(uuid4(), Modality.THERMAL, thermogram)

    assert result.prediction is prediction
    assert result.producing_model.model_id == "thermal_cora_v1"
    assert predictor.inputs == [thermogram]


def test_rejects_producing_model_context_for_the_wrong_modality() -> None:
    orchestrator = InferenceOrchestrator(EventBus())
    predictor = FakePredictor(Prediction(Modality.VISION, "visual_anomaly", 0.8))

    with pytest.raises(ProducingModelModalityMismatchError, match="audio producing-model"):
        orchestrator.register(
            Modality.VISION,
            predictor,
            input_type=VisionInput,
            producing_model=producing_model(Modality.AUDIO),
        )
