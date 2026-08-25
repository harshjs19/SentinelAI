import pytest

from domain.enums.modality import Modality
from modules.retriever.models import RetrievalLane
from modules.retriever.planner import RetrievalQueryPlanner
from tests.retriever.support import make_evidence_package


@pytest.mark.parametrize(
    ("code", "modality", "expected_fault_code"),
    [
        ("bearing_fault", Modality.TIMESERIES, "bearing_fault"),
        ("visual_anomaly", Modality.VISION, "visual_anomaly"),
        ("acoustic_anomaly", Modality.AUDIO, "acoustic_anomaly"),
    ],
)
def test_abnormal_finding_creates_exact_bounded_maintenance_intent(
    code: str,
    modality: Modality,
    expected_fault_code: str,
) -> None:
    queries = RetrievalQueryPlanner().plan(make_evidence_package(code, modality=modality))

    maintenance = [query for query in queries if query.lane is RetrievalLane.MAINTENANCE]
    assert [query.fault_code for query in maintenance] == [expected_fault_code]
    if code in {"visual_anomaly", "acoustic_anomaly"}:
        assert "bearing_fault" not in {query.fault_code for query in queries}
        assert "unidentified physical fault" in maintenance[0].text


def test_healthy_analysis_has_no_abnormal_maintenance_intent() -> None:
    queries = RetrievalQueryPlanner().plan(make_evidence_package("healthy"))

    assert queries[0].fault_code == "healthy"
    assert all(query.lane is not RetrievalLane.MAINTENANCE for query in queries)
    assert "bearing_fault" not in {query.fault_code for query in queries}


def test_insufficient_evidence_has_only_interpretation_intents() -> None:
    queries = RetrievalQueryPlanner().plan(make_evidence_package(None))

    assert [query.fault_code for query in queries] == [
        "insufficient_evidence",
        "evidence_limitations",
    ]
    assert all(query.lane is RetrievalLane.INTERPRETATION for query in queries)


def test_experimental_model_and_uncalibrated_confidence_create_interpretation_intents() -> None:
    queries = RetrievalQueryPlanner().plan(
        make_evidence_package("visual_anomaly", modality=Modality.VISION)
    )

    codes = [query.fault_code for query in queries]
    assert "experimental_model" in codes
    assert "confidence_semantics" in codes
    experimental = next(query for query in queries if query.fault_code == "experimental_model")
    assert "experimental vision model" in experimental.text


def test_unavailable_claims_never_become_query_terms() -> None:
    package = make_evidence_package("bearing_fault")
    queries = RetrievalQueryPlanner().plan(package)
    query_text = " ".join(query.text.lower() for query in queries)

    assert package.claim_support.failure_probability_available is False
    assert package.claim_support.fault_severity_available is False
    assert package.claim_support.operational_risk_available is False
    assert "failure probability" not in query_text
    assert "severity" not in query_text
    assert "risk" not in query_text
