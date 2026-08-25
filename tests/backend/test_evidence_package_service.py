import builtins
from datetime import UTC, datetime
from uuid import UUID

import pytest

import backend.app.dependencies as dependencies
from backend.app.services.evidence_package_service import EvidencePackageService
from domain.entities.analysis import Analysis
from domain.entities.finding import Finding
from domain.entities.machine import Machine
from domain.entities.prediction import Prediction
from domain.enums.analysis_status import AnalysisStatus
from domain.enums.condition_state import ConditionState
from domain.enums.confidence_kind import ConfidenceKind
from domain.enums.modality import Modality
from inference.orchestrator import InferenceOrchestrator
from modules.decision.engine import DecisionEngine
from shared.evidence.models import verify_evidence_package_digest
from shared.evidence.provenance import structured_source_provenance


def test_service_builds_without_models_decision_engine_database_or_file_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("EvidencePackageService crossed an external runtime boundary")

    for provider_name in (
        "get_timeseries_predictor",
        "get_audio_predictor",
        "get_vision_predictor",
        "get_thermal_predictor",
        "get_inference_orchestrator",
        "get_decision_engine",
        "get_machine_service",
    ):
        monkeypatch.setattr(dependencies, provider_name, unexpected_call)
    monkeypatch.setattr(InferenceOrchestrator, "predict", unexpected_call)
    monkeypatch.setattr(DecisionEngine, "evaluate", unexpected_call)

    machine_id = UUID("00000000-0000-0000-0000-000000000301")
    prediction = Prediction(Modality.TIMESERIES, "bearing_fault", 0.88)
    analysis = Analysis(
        id=UUID("00000000-0000-0000-0000-000000000302"),
        machine_id=machine_id,
        predictions=(prediction,),
        findings=(
            Finding(
                modality=prediction.modality,
                code=prediction.label,
                condition=ConditionState.ABNORMAL,
                confidence=prediction.confidence,
                confidence_kind=ConfidenceKind.RAW,
            ),
        ),
        condition=ConditionState.ABNORMAL,
        status=AnalysisStatus.PROVISIONAL,
        health_score=None,
        risk_level=None,
        limitations=(),
        created_at=datetime(2026, 8, 25, 9, 0, tzinfo=UTC),
    )
    source = structured_source_provenance(
        Modality.TIMESERIES,
        {"samples": [{"ch1": 1.0}, {"ch1": 2.0}]},
    )
    monkeypatch.setattr(builtins, "open", unexpected_call)

    package = EvidencePackageService().build(
        Machine(machine_id, "Synthetic motor", "motor"),
        analysis,
        [source],
    )

    assert package.models[0].model_id == "timeseries_utk_v1"
    assert package.models[0].evaluation_reference == ("evaluation/timeseries_baseline_results.json")
    assert verify_evidence_package_digest(package)
