from datetime import UTC
from uuid import uuid4

from domain.entities.analysis import Analysis
from domain.entities.finding import Finding
from domain.entities.prediction import Prediction
from domain.enums.analysis_limitation import AnalysisLimitation
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from domain.enums.modality import Modality


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
