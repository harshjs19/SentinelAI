from datetime import UTC, datetime
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
from domain.enums.risk_level import RiskLevel
from domain.value_objects.health_score import HealthScore


def _finding() -> Finding:
    return Finding(
        modality=Modality.TIMESERIES,
        code="bearing_fault",
        condition=ConditionState.ABNORMAL,
        confidence=0.9,
        confidence_kind=ConfidenceKind.RAW,
    )


def test_creates_provisional_analysis_with_unavailable_health_and_risk() -> None:
    prediction = Prediction(Modality.TIMESERIES, "bearing_fault", 0.87)
    finding = Finding(
        modality=Modality.TIMESERIES,
        code="bearing_fault",
        condition=ConditionState.ABNORMAL,
        confidence=0.87,
        confidence_kind=ConfidenceKind.RAW,
    )

    analysis = Analysis(
        id=uuid4(),
        machine_id=uuid4(),
        predictions=(prediction,),
        findings=(finding,),
        condition=ConditionState.ABNORMAL,
        status=AnalysisStatus.PROVISIONAL,
        health_score=None,
        risk_level=None,
        limitations=(AnalysisLimitation.UNCALIBRATED_CONFIDENCE,),
    )

    assert analysis.predictions == (prediction,)
    assert analysis.findings == (finding,)
    assert analysis.health_score is None
    assert analysis.risk_level is None
    assert analysis.created_at.tzinfo is UTC


def test_allows_empty_evidence_for_insufficient_analysis() -> None:
    analysis = Analysis(
        id=uuid4(),
        machine_id=uuid4(),
        predictions=(),
        findings=(),
        condition=ConditionState.INDETERMINATE,
        status=AnalysisStatus.INSUFFICIENT_EVIDENCE,
        health_score=None,
        risk_level=None,
        limitations=(),
    )

    assert analysis.predictions == ()
    assert analysis.findings == ()
    assert analysis.top_findings == ()


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"status": AnalysisStatus.PROVISIONAL}, "insufficient-evidence status"),
        ({"status": AnalysisStatus.COMPLETE}, "insufficient-evidence status"),
        ({"condition": ConditionState.ABNORMAL}, "indeterminate condition"),
        ({"findings": (_finding(),)}, "cannot contain findings"),
        ({"health_score": HealthScore(80)}, "cannot contain a health score"),
        ({"risk_level": RiskLevel.HIGH}, "cannot contain a risk level"),
        (
            {"limitations": (AnalysisLimitation.RISK_CONTEXT_UNAVAILABLE,)},
            "cannot contain limitations",
        ),
    ],
)
def test_rejects_contradictory_no_evidence_state(
    override: dict[str, object],
    message: str,
) -> None:
    values = {
        "id": uuid4(),
        "machine_id": uuid4(),
        "predictions": (),
        "findings": (),
        "condition": ConditionState.INDETERMINATE,
        "status": AnalysisStatus.INSUFFICIENT_EVIDENCE,
        "health_score": None,
        "risk_level": None,
        "limitations": (),
    }
    values.update(override)

    with pytest.raises(ValueError, match=message):
        Analysis(**values)  # type: ignore[arg-type]


def test_rejects_insufficient_evidence_status_when_prediction_exists() -> None:
    with pytest.raises(ValueError, match="with predictions"):
        Analysis(
            id=uuid4(),
            machine_id=uuid4(),
            predictions=(Prediction(Modality.TIMESERIES, "healthy", 0.9),),
            findings=(),
            condition=ConditionState.INDETERMINATE,
            status=AnalysisStatus.INSUFFICIENT_EVIDENCE,
            health_score=None,
            risk_level=None,
            limitations=(),
        )


def test_rejects_non_utc_created_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        Analysis(
            id=uuid4(),
            machine_id=uuid4(),
            predictions=(),
            findings=(),
            condition=ConditionState.INDETERMINATE,
            status=AnalysisStatus.INSUFFICIENT_EVIDENCE,
            health_score=None,
            risk_level=None,
            limitations=(),
            created_at=datetime.now(),
        )
