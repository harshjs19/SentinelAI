import httpx
import pytest

import backend.app.dependencies as dependencies
from backend.app.main import app


@pytest.mark.asyncio
async def test_lists_declared_model_capabilities_in_deterministic_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_provider_call() -> None:
        raise AssertionError("Capability metadata must not load models or query the database")

    provider_names = (
        "get_timeseries_predictor",
        "get_audio_predictor",
        "get_vision_predictor",
        "get_thermal_predictor",
        "get_machine_service",
    )
    providers = tuple(getattr(dependencies, name) for name in provider_names)
    for provider in providers:
        app.dependency_overrides[provider] = unexpected_provider_call
    for provider_name in provider_names:
        monkeypatch.setattr(dependencies, provider_name, unexpected_provider_call)

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.get("/capabilities/models")
            second = await client.get("/capabilities/models")
    finally:
        for provider in providers:
            app.dependency_overrides.pop(provider, None)

    assert first.status_code == 200
    assert second.json() == first.json()
    assert first.json() == {
        "models": [
            {
                "model_id": "timeseries_utk_v1",
                "modality": "timeseries",
                "status": "validated_baseline",
                "runtime_default": True,
                "validated_scope": (
                    "UTK blocked chronological within-recording multiclass evaluation"
                ),
                "evaluation_reference": "evaluation/timeseries_baseline_results.json",
                "confidence_semantics": "raw_selected_class_predict_proba",
            },
            {
                "model_id": "audio_mimii_v1",
                "modality": "audio",
                "status": "experimental",
                "runtime_default": True,
                "validated_scope": ("MIMII DG bearing held-out Section 02 domain-shift evaluation"),
                "evaluation_reference": "evaluation/audio_baseline_results.json",
                "confidence_semantics": (
                    "bounded_empirical_anomaly_evidence_from_normal_calibration"
                ),
            },
            {
                "model_id": "audio_mimii_ast_v2",
                "modality": "audio",
                "status": "rejected_experiment",
                "runtime_default": False,
                "validated_scope": "MIMII DG frozen-AST Section 01 promotion experiment",
                "evaluation_reference": "evaluation/audio_v2_results.json",
                "confidence_semantics": (
                    "bounded_empirical_anomaly_evidence_from_normal_calibration"
                ),
            },
            {
                "model_id": "vision_visa_pcb1_v1",
                "modality": "vision",
                "status": "experimental",
                "runtime_default": True,
                "validated_scope": "VisA PCB1 official one-class split evaluation",
                "evaluation_reference": "evaluation/vision_baseline_results.json",
                "confidence_semantics": (
                    "bounded_empirical_visual_anomaly_evidence_from_normal_calibration"
                ),
            },
            {
                "model_id": "thermal_cora_v1",
                "modality": "thermal",
                "status": "experimental",
                "runtime_default": True,
                "validated_scope": "CORA same-test-bench operating-speed-held-out evaluation",
                "evaluation_reference": "evaluation/thermal_baseline_results.json",
                "confidence_semantics": "raw_selected_class_predict_proba",
            },
        ]
    }
