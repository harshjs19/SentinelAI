import pytest

from domain.entities.prediction import Prediction
from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from domain.enums.modality import Modality
from modules.decision.exceptions import (
    UnsupportedPredictionLabelError,
    UnsupportedPredictionModalityError,
)
from modules.decision.normalizer import normalize_prediction


def test_normalizes_healthy_timeseries_prediction() -> None:
    finding = normalize_prediction(Prediction(Modality.TIMESERIES, "healthy", 0.76))

    assert finding.code == "healthy"
    assert finding.condition is ConditionState.NORMAL
    assert finding.confidence == 0.76
    assert finding.confidence_kind is ConfidenceKind.RAW


@pytest.mark.parametrize(
    "label",
    [
        "bearing_fault",
        "coupling_fault",
        "bent_shaft",
        "eccentric_rotor",
        "imbalance",
    ],
)
def test_normalizes_known_fault_as_abnormal(label: str) -> None:
    finding = normalize_prediction(Prediction(Modality.TIMESERIES, label, 0.91))

    assert finding.code == label
    assert finding.condition is ConditionState.ABNORMAL
    assert finding.confidence == 0.91
    assert finding.confidence_kind is ConfidenceKind.RAW


def test_rejects_unknown_timeseries_label() -> None:
    with pytest.raises(UnsupportedPredictionLabelError, match="unknown_fault"):
        normalize_prediction(Prediction(Modality.TIMESERIES, "unknown_fault", 0.7))


@pytest.mark.parametrize(
    ("label", "condition"),
    [
        ("healthy", ConditionState.NORMAL),
        ("acoustic_anomaly", ConditionState.ABNORMAL),
    ],
)
def test_normalizes_audio_evidence_without_inventing_fault_type(
    label: str,
    condition: ConditionState,
) -> None:
    finding = normalize_prediction(Prediction(Modality.AUDIO, label, 0.88))

    assert finding.code == label
    assert finding.condition is condition
    assert finding.confidence == 0.88
    assert finding.confidence_kind is ConfidenceKind.RAW


def test_rejects_unknown_audio_label() -> None:
    with pytest.raises(UnsupportedPredictionLabelError, match="bearing_fault"):
        normalize_prediction(Prediction(Modality.AUDIO, "bearing_fault", 0.7))


def test_rejects_unsupported_modality() -> None:
    with pytest.raises(UnsupportedPredictionModalityError, match="vision"):
        normalize_prediction(Prediction(Modality.VISION, "anomaly", 0.7))
