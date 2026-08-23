from dataclasses import dataclass
from uuid import UUID

from domain.entities.prediction import Prediction


@dataclass(frozen=True)
class PredictionProduced:
    machine_id: UUID
    prediction: Prediction
