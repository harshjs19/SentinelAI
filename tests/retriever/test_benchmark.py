import json
from pathlib import Path

from modules.retriever.config import MANIFEST_PATH, REPOSITORY_ROOT, SUPPORTED_FAULT_CODES
from modules.retriever.manifest import load_manifest


def test_regression_benchmark_has_unique_required_scenarios() -> None:
    benchmark = json.loads(Path("evaluation/retriever_queries.json").read_text(encoding="utf-8"))
    cases = benchmark["cases"]
    case_ids = [case["query_case_id"] for case in cases]

    assert benchmark["schema_version"] == "1"
    assert len(case_ids) == len(set(case_ids)) == 11
    assert {
        "bearing_fault",
        "imbalance",
        "misalignment",
        "half_broken_rotor_bar",
        "gear_wear_75",
        "visual_anomaly",
        "acoustic_anomaly",
        "healthy",
        "insufficient_evidence",
        "experimental_model",
        "confidence_semantics",
    } == {case["target_fault_code"] for case in cases}


def test_tracked_corpus_covers_every_declared_v1_fault_and_interpretation_code() -> None:
    sources = load_manifest(MANIFEST_PATH, repository_root=REPOSITORY_ROOT)
    coverage = {fault_code for source in sources for fault_code in source.fault_codes}

    assert coverage == SUPPORTED_FAULT_CODES


def test_real_baseline_records_safety_and_citation_regressions_without_local_paths() -> None:
    path = Path("evaluation/retriever_baseline_results.json")
    baseline = json.loads(path.read_text(encoding="utf-8"))
    serialized = path.read_text(encoding="utf-8")
    cases = {case["query_case_id"]: case for case in baseline["cases"]}

    assert baseline["metrics"]["citation_completeness"] == 1.0
    assert baseline["metrics"]["cross_fault_contamination_count"] == 0
    assert cases["healthy_interpretation"]["has_fault_specific_maintenance"] is False
    assert cases["insufficient_evidence_boundary"]["has_fault_specific_maintenance"] is False
    assert cases["visual_anomaly_boundary"]["top_target_chunks"][0]["fault_code"] == (
        "visual_anomaly"
    )
    assert cases["acoustic_anomaly_boundary"]["top_target_chunks"][0]["fault_code"] == (
        "acoustic_anomaly"
    )
    assert "D:\\\\Projects" not in serialized
    assert "knowledge/chroma" not in serialized
    assert "knowledge/embeddings" not in serialized
