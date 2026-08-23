import io
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image

from backend.app.services.vision_inference_service import (
    UnsupportedVisionAssetTypeError,
    VisionInferenceService,
)
from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from inference.event_bus import EventBus
from inference.events import PredictionProduced
from inference.orchestrator import InferenceOrchestrator
from modules.vision.input import VisionInput


class RecordingVisionPredictor:
    def __init__(self) -> None:
        self.inputs: list[VisionInput] = []

    def predict(self, input_data: VisionInput) -> Prediction:
        self.inputs.append(input_data)
        return Prediction(Modality.VISION, "healthy", 0.8)


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(np.zeros((6, 8, 3), dtype=np.uint8), mode="RGB").save(buffer, "PNG")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_decodes_image_and_emits_prediction_event() -> None:
    event_bus = EventBus()
    orchestrator = InferenceOrchestrator(event_bus)
    predictor = RecordingVisionPredictor()
    orchestrator.register(Modality.VISION, predictor, input_type=VisionInput)
    service = VisionInferenceService(orchestrator, ("pcb1",))
    events: list[PredictionProduced] = []

    async def record(event: PredictionProduced) -> None:
        events.append(event)

    event_bus.subscribe(PredictionProduced, record)
    machine_id = uuid4()

    prediction = await service.predict(machine_id, png_bytes())

    assert prediction == Prediction(Modality.VISION, "healthy", 0.8)
    assert predictor.inputs[0].pixels.shape == (6, 8, 3)
    assert events == [PredictionProduced(machine_id, prediction)]


def test_rejects_unsupported_asset_type() -> None:
    service = VisionInferenceService(InferenceOrchestrator(EventBus()), ("pcb1",))

    with pytest.raises(UnsupportedVisionAssetTypeError, match="pcb1"):
        service.validate_asset_type("bearing")
