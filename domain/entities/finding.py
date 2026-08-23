from dataclasses import dataclass

from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from domain.enums.modality import Modality


@dataclass(frozen=True)
class Finding:
    modality: Modality
    code: str
    condition: ConditionState
    confidence: float
    confidence_kind: ConfidenceKind

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("Finding code cannot be empty")
        if not 0 <= self.confidence <= 1:
            raise ValueError("Finding confidence must be between 0 and 1")
