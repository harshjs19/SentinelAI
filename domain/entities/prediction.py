from dataclasses import dataclass

from domain.enums.modality import Modality


@dataclass(frozen=True)
class Prediction:
    modality: Modality
    label: str
    confidence: float

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("Prediction label cannot be empty")

        if not 0 <= self.confidence <= 1:
            raise ValueError("Prediction confidence must be between 0 and 1")
