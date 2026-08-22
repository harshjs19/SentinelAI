import pytest

from domain.entities.prediction import Prediction
from domain.enums.modality import Modality


def test_creates_prediction() -> None:
    prediction = Prediction(
        modality=Modality.AUDIO,
        label="bearing_fault",
        confidence=0.87,
    )

    assert prediction.modality is Modality.AUDIO
    assert prediction.label == "bearing_fault"
    assert prediction.confidence == 0.87


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_rejects_invalid_confidence(confidence: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        Prediction(
            modality=Modality.AUDIO,
            label="bearing_fault",
            confidence=confidence,
        )


def test_rejects_empty_label() -> None:
    with pytest.raises(ValueError, match="label cannot be empty"):
        Prediction(
            modality=Modality.AUDIO,
            label="   ",
            confidence=0.8,
        )
