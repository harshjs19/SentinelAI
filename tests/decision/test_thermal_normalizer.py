from uuid import uuid4

import pytest

from domain.entities.prediction import Prediction
from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from domain.enums.modality import Modality
from modules.decision.engine import DecisionEngine
from modules.decision.exceptions import UnsupportedPredictionLabelError
from modules.decision.normalizer import normalize_prediction


@pytest.mark.parametrize(
    ("label", "condition"),
    [
        ("healthy", ConditionState.NORMAL),
        ("bearing_fault", ConditionState.ABNORMAL),
        ("imbalance", ConditionState.ABNORMAL),
        ("half_broken_rotor_bar", ConditionState.ABNORMAL),
        ("broken_rotor_bar", ConditionState.ABNORMAL),
        ("misalignment", ConditionState.ABNORMAL),
        ("gear_wear_25", ConditionState.ABNORMAL),
        ("gear_wear_50", ConditionState.ABNORMAL),
        ("gear_wear_75", ConditionState.ABNORMAL),
    ],
)
def test_normalizes_supported_thermal_condition(
    label: str,
    condition: ConditionState,
) -> None:
    finding = normalize_prediction(Prediction(Modality.THERMAL, label, 0.9))

    assert finding.code == label
    assert finding.condition is condition
    assert finding.confidence_kind is ConfidenceKind.RAW


def test_rejects_unknown_thermal_label() -> None:
    with pytest.raises(UnsupportedPredictionLabelError, match="unknown_thermal_fault"):
        normalize_prediction(Prediction(Modality.THERMAL, "unknown_thermal_fault", 0.7))


def test_high_confidence_gear_wear_does_not_create_health_or_risk() -> None:
    analysis = DecisionEngine().evaluate(
        uuid4(),
        [Prediction(Modality.THERMAL, "gear_wear_75", 0.99)],
    )

    assert analysis.condition is ConditionState.ABNORMAL
    assert analysis.health_score is None
    assert analysis.risk_level is None
