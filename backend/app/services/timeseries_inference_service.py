from collections.abc import Mapping, Sequence
from uuid import UUID

import pandas as pd

from domain.enums.modality import Modality
from inference.orchestrator import InferenceOrchestrator
from inference.result import InferenceResult
from modules.timeseries.data import extract_window_features


class TimeseriesInferenceService:
    def __init__(self, orchestrator: InferenceOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def predict(
        self,
        machine_id: UUID,
        samples: Sequence[Mapping[str, float]],
    ) -> InferenceResult:
        if len(samples) < 2:
            raise ValueError("A time-series window requires at least two samples")

        features = extract_window_features(pd.DataFrame(samples))
        return await self._orchestrator.predict(
            machine_id,
            Modality.TIMESERIES,
            features,
        )
