from datetime import UTC
from uuid import uuid4

import pytest

from domain.entities.analysis import Analysis
from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from domain.enums.risk_level import RiskLevel
from domain.value_objects.health_score import HealthScore


def test_creates_analysis() -> None:
    prediction = Prediction(
        modality=Modality.AUDIO,
        label="bearing_fault",
        confidence=0.87,
    )

    analysis = Analysis(
        id=uuid4(),
        machine_id=uuid4(),
        predictions=(prediction,),
        health_score=HealthScore(72),
        risk_level=RiskLevel.HIGH,
    )

    assert analysis.predictions == (prediction,)
    assert analysis.health_score == HealthScore(72)
    assert analysis.risk_level is RiskLevel.HIGH
    assert analysis.created_at.tzinfo is UTC


def test_requires_at_least_one_prediction() -> None:
    with pytest.raises(
        ValueError,
        match="Analysis must contain at least one prediction",
    ):
        Analysis(
            id=uuid4(),
            machine_id=uuid4(),
            predictions=(),
            health_score=HealthScore(90),
            risk_level=RiskLevel.LOW,
        )
