import io
from uuid import uuid4

import numpy as np
import pytest
import soundfile as sf

from ai_core.model_capabilities import get_runtime_default_capability
from ai_core.model_provenance import snapshot_producing_model_context
from backend.app.services.audio_inference_service import (
    AudioInferenceService,
    UnsupportedAudioAssetTypeError,
)
from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from inference.event_bus import EventBus
from inference.events import PredictionProduced
from inference.orchestrator import InferenceOrchestrator
from modules.audio.input import AudioInput


class RecordingAudioPredictor:
    def __init__(self) -> None:
        self.inputs: list[AudioInput] = []

    def predict(self, input_data: AudioInput) -> Prediction:
        self.inputs.append(input_data)
        return Prediction(Modality.AUDIO, "healthy", 0.81)


def wav_bytes() -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, np.zeros(1_600), 16_000, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_decodes_audio_and_emits_prediction_event() -> None:
    event_bus = EventBus()
    orchestrator = InferenceOrchestrator(event_bus)
    predictor = RecordingAudioPredictor()
    orchestrator.register(
        Modality.AUDIO,
        predictor,
        input_type=AudioInput,
        producing_model=snapshot_producing_model_context(
            get_runtime_default_capability(Modality.AUDIO)
        ),
    )
    service = AudioInferenceService(orchestrator, ("bearing",))
    events: list[PredictionProduced] = []

    async def record(event: PredictionProduced) -> None:
        events.append(event)

    event_bus.subscribe(PredictionProduced, record)
    machine_id = uuid4()

    result = await service.predict(machine_id, wav_bytes())

    assert result.prediction == Prediction(Modality.AUDIO, "healthy", 0.81)
    assert result.producing_model.model_id == "audio_mimii_v1"
    assert len(predictor.inputs) == 1
    assert predictor.inputs[0].sample_rate == 16_000
    assert events == [PredictionProduced(machine_id, result.prediction)]


def test_rejects_unsupported_asset_type() -> None:
    service = AudioInferenceService(InferenceOrchestrator(EventBus()), ("bearing",))

    with pytest.raises(UnsupportedAudioAssetTypeError, match="bearing"):
        service.validate_asset_type("pump")


@pytest.mark.asyncio
async def test_rejects_malformed_audio() -> None:
    service = AudioInferenceService(InferenceOrchestrator(EventBus()), ("bearing",))

    with pytest.raises(ValueError, match="valid WAV"):
        await service.predict(uuid4(), b"not-a-wav")
