from dataclasses import dataclass
from uuid import UUID

from domain.entities.analysis import Analysis
from domain.entities.prediction import Prediction


@dataclass(frozen=True)
class PredictionProduced:
    machine_id: UUID
    prediction: Prediction


@dataclass(frozen=True)
class AnalysisProduced:
    machine_id: UUID
    analysis: Analysis
