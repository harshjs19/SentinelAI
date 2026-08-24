from uuid import uuid4

import pytest

from domain.entities.analysis import Analysis
from domain.entities.finding import Finding
from domain.entities.prediction import Prediction
from domain.enums.analysis_limitation import AnalysisLimitation
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from domain.enums.modality import Modality
from modules.decision.engine import DecisionEngine
from modules.decision.exceptions import (
    DuplicateModalityPredictionError,
    UnsupportedPredictionLabelError,
)


def test_healthy_prediction_produces_normal_provisional_analysis() -> None:
    analysis = DecisionEngine().evaluate(
        uuid4(),
        [Prediction(Modality.TIMESERIES, "healthy", 0.84)],
    )

    assert analysis.condition is ConditionState.NORMAL
    assert analysis.status is AnalysisStatus.PROVISIONAL
    assert analysis.limitations == (
        AnalysisLimitation.UNCALIBRATED_CONFIDENCE,
        AnalysisLimitation.RISK_CONTEXT_UNAVAILABLE,
        AnalysisLimitation.SINGLE_MODALITY_EVIDENCE,
    )


def test_high_confidence_fault_does_not_fabricate_health_or_risk() -> None:
    prediction = Prediction(Modality.TIMESERIES, "bearing_fault", 0.99)

    analysis = DecisionEngine().evaluate(uuid4(), [prediction])

    assert analysis.condition is ConditionState.ABNORMAL
    assert analysis.status is AnalysisStatus.PROVISIONAL
    assert analysis.findings == (
        Finding(
            modality=Modality.TIMESERIES,
            code="bearing_fault",
            condition=ConditionState.ABNORMAL,
            confidence=0.99,
            confidence_kind=ConfidenceKind.RAW,
        ),
    )
    assert analysis.health_score is None
    assert analysis.risk_level is None
    assert analysis.limitations == (
        AnalysisLimitation.UNCALIBRATED_CONFIDENCE,
        AnalysisLimitation.FAULT_SEVERITY_UNAVAILABLE,
        AnalysisLimitation.RISK_CONTEXT_UNAVAILABLE,
        AnalysisLimitation.SINGLE_MODALITY_EVIDENCE,
    )


@pytest.mark.parametrize(
    ("modality", "label"),
    [
        (Modality.AUDIO, "acoustic_anomaly"),
        (Modality.VISION, "visual_anomaly"),
    ],
)
def test_high_confidence_anomaly_does_not_fabricate_health_or_risk(
    modality: Modality,
    label: str,
) -> None:
    analysis = DecisionEngine().evaluate(uuid4(), [Prediction(modality, label, 0.99)])

    assert analysis.condition is ConditionState.ABNORMAL
    assert analysis.health_score is None
    assert analysis.risk_level is None


def test_no_predictions_produces_insufficient_indeterminate_analysis() -> None:
    analysis = DecisionEngine().evaluate(uuid4(), [])

    assert analysis.condition is ConditionState.INDETERMINATE
    assert analysis.status is AnalysisStatus.INSUFFICIENT_EVIDENCE
    assert analysis.predictions == ()
    assert analysis.findings == ()
    assert analysis.health_score is None
    assert analysis.risk_level is None
    assert analysis.limitations == ()


def test_rejects_duplicate_modality_predictions() -> None:
    predictions = [
        Prediction(Modality.TIMESERIES, "healthy", 0.8),
        Prediction(Modality.TIMESERIES, "bearing_fault", 0.7),
    ]

    with pytest.raises(DuplicateModalityPredictionError, match="timeseries"):
        DecisionEngine().evaluate(uuid4(), predictions)


def test_rejects_unsupported_label() -> None:
    with pytest.raises(UnsupportedPredictionLabelError, match="unknown_fault"):
        DecisionEngine().evaluate(
            uuid4(),
            [Prediction(Modality.TIMESERIES, "unknown_fault", 0.7)],
        )


def test_top_findings_rank_deterministically_and_return_at_most_three() -> None:
    findings = (
        _finding(Modality.VISION, "normal", ConditionState.NORMAL, 1.0),
        _finding(Modality.TIMESERIES, "lower", ConditionState.ABNORMAL, 0.8),
        _finding(Modality.AUDIO, "z_code", ConditionState.ABNORMAL, 0.9),
        _finding(Modality.AUDIO, "a_code", ConditionState.ABNORMAL, 0.9),
        _finding(Modality.THERMAL, "thermal", ConditionState.ABNORMAL, 0.9),
    )
    analysis = Analysis(
        id=uuid4(),
        machine_id=uuid4(),
        predictions=tuple(
            Prediction(finding.modality, finding.code, finding.confidence) for finding in findings
        ),
        findings=findings,
        condition=ConditionState.ABNORMAL,
        status=AnalysisStatus.PROVISIONAL,
        health_score=None,
        risk_level=None,
        limitations=(),
    )

    assert [finding.code for finding in analysis.top_findings] == [
        "a_code",
        "z_code",
        "thermal",
    ]


def _finding(
    modality: Modality,
    code: str,
    condition: ConditionState,
    confidence: float,
) -> Finding:
    return Finding(
        modality=modality,
        code=code,
        condition=condition,
        confidence=confidence,
        confidence_kind=ConfidenceKind.RAW,
    )
