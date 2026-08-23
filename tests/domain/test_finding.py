import pytest

from domain.entities.finding import Finding
from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from domain.enums.modality import Modality


def test_creates_finding() -> None:
    finding = Finding(
        modality=Modality.TIMESERIES,
        code="bearing_fault",
        condition=ConditionState.ABNORMAL,
        confidence=0.91,
        confidence_kind=ConfidenceKind.RAW,
    )

    assert finding.code == "bearing_fault"
    assert finding.confidence == 0.91


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_rejects_confidence_outside_bounds(confidence: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        Finding(
            modality=Modality.TIMESERIES,
            code="healthy",
            condition=ConditionState.NORMAL,
            confidence=confidence,
            confidence_kind=ConfidenceKind.RAW,
        )


def test_rejects_blank_code() -> None:
    with pytest.raises(ValueError, match="code cannot be empty"):
        Finding(
            modality=Modality.TIMESERIES,
            code="   ",
            condition=ConditionState.NORMAL,
            confidence=0.8,
            confidence_kind=ConfidenceKind.RAW,
        )
