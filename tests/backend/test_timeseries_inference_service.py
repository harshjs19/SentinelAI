from collections.abc import Mapping
from uuid import uuid4

import pytest

from ai_core.model_capabilities import get_runtime_default_capability
from ai_core.model_provenance import snapshot_producing_model_context
from backend.app.services.timeseries_inference_service import TimeseriesInferenceService
from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from inference.event_bus import EventBus
from inference.orchestrator import InferenceOrchestrator
from modules.timeseries.config import FEATURE_NAMES, RAW_FEATURES


class RecordingPredictor:
    def __init__(self) -> None:
        self.features: Mapping[str, float] | None = None

    def predict(self, input_data: Mapping[str, float]) -> Prediction:
        self.features = input_data
        return Prediction(Modality.TIMESERIES, "healthy", 0.88)


def sample(value: float) -> dict[str, float]:
    return {feature: value for feature in RAW_FEATURES}


@pytest.fixture
def service_and_predictor() -> tuple[TimeseriesInferenceService, RecordingPredictor]:
    predictor = RecordingPredictor()
    orchestrator = InferenceOrchestrator(EventBus())
    orchestrator.register(
        Modality.TIMESERIES,
        predictor,
        input_type=Mapping,
        producing_model=snapshot_producing_model_context(
            get_runtime_default_capability(Modality.TIMESERIES)
        ),
    )
    return TimeseriesInferenceService(orchestrator), predictor


@pytest.mark.asyncio
async def test_converts_raw_samples_and_returns_domain_prediction(
    service_and_predictor: tuple[TimeseriesInferenceService, RecordingPredictor],
) -> None:
    service, predictor = service_and_predictor

    result = await service.predict(uuid4(), [sample(1.0), sample(3.0)])

    assert result.prediction == Prediction(Modality.TIMESERIES, "healthy", 0.88)
    assert result.producing_model.model_id == "timeseries_utk_v1"
    assert predictor.features is not None
    assert set(predictor.features) == set(FEATURE_NAMES)
    assert predictor.features["ch1_bias_mean"] == 2.0
    assert predictor.features["ch1_bias_std"] == pytest.approx(2**0.5)


@pytest.mark.asyncio
async def test_rejects_empty_window(
    service_and_predictor: tuple[TimeseriesInferenceService, RecordingPredictor],
) -> None:
    service, _ = service_and_predictor

    with pytest.raises(ValueError, match="at least two samples"):
        await service.predict(uuid4(), [])


@pytest.mark.asyncio
async def test_rejects_malformed_sample(
    service_and_predictor: tuple[TimeseriesInferenceService, RecordingPredictor],
) -> None:
    service, _ = service_and_predictor

    with pytest.raises(ValueError, match="Missing raw features"):
        await service.predict(uuid4(), [{"ch1_bias": 1.0}, {"ch1_bias": 2.0}])
