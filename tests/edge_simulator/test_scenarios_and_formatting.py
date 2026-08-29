from pathlib import Path

import pytest

from edge_simulator.client import SimulatorError
from edge_simulator.formatting import format_evidence, format_outcome, format_report
from edge_simulator.models import EdgeObservation, ScenarioOutcome, SubmissionReceipt
from edge_simulator.scenarios import SCENARIOS, run_scenario

MACHINE_ID = "11111111-1111-4111-8111-111111111111"
REPORT_ID = "22222222-2222-4222-8222-222222222222"


class RecordingClient:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self.documents = documents
        self.calls: list[tuple[EdgeObservation, str, str | None, str]] = []

    def new_idempotency_key(self) -> str:
        return "33333333-3333-4333-8333-333333333333"

    def submit_report(
        self,
        machine_id: str,
        observation: EdgeObservation,
        *,
        intent: str,
        question: str | None = None,
        idempotency_key: str | None = None,
    ) -> SubmissionReceipt:
        assert machine_id == MACHINE_ID
        assert idempotency_key is not None
        self.calls.append((observation, intent, question, idempotency_key))
        index = len(self.calls) - 1
        document = self.documents[min(index, len(self.documents) - 1)]
        return SubmissionReceipt(
            status_code=201 if index == 0 else 200,
            report_id=str(document.get("report_id", REPORT_ID)),
            replayed=index > 0,
            idempotency_key=idempotency_key,
            document=document,
        )


def test_idempotent_scenario_reuses_exact_observation_and_key() -> None:
    client = RecordingClient([{"report_id": REPORT_ID}])

    outcome = run_scenario(  # type: ignore[arg-type]
        client,
        SCENARIOS["idempotent_replay"],
        MACHINE_ID,
    )

    assert len(client.calls) == 2
    assert client.calls[0] == client.calls[1]
    assert outcome.receipt.replayed
    assert "same stored report" in outcome.notes[0]


@pytest.mark.parametrize(
    ("scenario_name", "fallback_reason"),
    [
        ("high_impact_safe_request", "unsupported_request"),
        ("provider_unavailable_fallback", "generation_unavailable"),
    ],
)
def test_safe_fallback_scenarios_verify_backend_outcome(
    scenario_name: str,
    fallback_reason: str,
) -> None:
    client = RecordingClient([{"report_id": REPORT_ID, "fallback_reason": fallback_reason}])

    outcome = run_scenario(client, SCENARIOS[scenario_name], MACHINE_ID)  # type: ignore[arg-type]

    assert fallback_reason in outcome.notes[0]


def test_fallback_scenario_fails_if_backend_does_not_confirm_expected_reason() -> None:
    client = RecordingClient([{"report_id": REPORT_ID, "fallback_reason": None}])
    with pytest.raises(SimulatorError, match="expected fallback_reason"):
        run_scenario(  # type: ignore[arg-type]
            client,
            SCENARIOS["provider_unavailable_fallback"],
            MACHINE_ID,
        )


def test_report_format_preserves_scientific_boundaries_and_model_lifecycle() -> None:
    document = {
        "report_id": REPORT_ID,
        "machine_id": MACHINE_ID,
        "generation_status": "fallback",
        "fallback_reason": "generation_unavailable",
        "request_disposition": "answered",
        "analysis": {
            "condition": "attention",
            "status": "complete",
            "findings": [
                {
                    "code": "vibration_pattern",
                    "condition": "attention",
                    "confidence": 0.81,
                    "confidence_kind": "raw_classifier_probability",
                }
            ],
        },
        "narrative": {
            "executive_summary": "Stored report summary",
            "inspection_considerations": [{"text": "Consider inspecting mounting."}],
        },
        "limitations": {"unavailable_claims": ["failure_probability"]},
        "producing_models": [
            {
                "model_id": "timeseries_utk_v1",
                "modality": "timeseries",
                "status": "experimental",
                "validated_scope": "laboratory recordings",
                "confidence_semantics": "raw classifier output",
            }
        ],
    }

    output = format_report(document)

    assert "Model confidence is not failure probability" in output
    assert "severity" in output
    assert "operational risk" in output
    assert "RUL" in output
    assert "Inspection Considerations (non-directive)" in output
    assert "experimental" in output
    assert "failure_probability" in output


def test_evidence_format_is_safe_metadata_only_and_sanitizes_terminal_controls() -> None:
    secret_path = r"D:\private\source.wav"
    document = {
        "report": {
            "report_id": REPORT_ID,
            "report_digest_sha256": "a" * 64,
            "schema_version": "1",
        },
        "analysis": {
            "analysis_id": "analysis\x1b[31m",
            "condition": "normal",
            "status": "complete",
        },
        "evidence_package": {
            "package_id": "evp1_safe",
            "package_digest_sha256": "b" * 64,
            "schema_version": "1",
        },
        "retrieval_bundle": {
            "retrieval_bundle_digest_sha256": "c" * 64,
            "schema_version": "1",
            "corpus_digest_sha256": "d" * 64,
            "embedding_model_id": "local-model",
            "embedding_model_revision": "pinned",
        },
        "sources": [
            {
                "modality": "timeseries",
                "source_kind": "inline_samples",
                "sha256": "e" * 64,
                "size_bytes": 123,
                "content_type": "application/json",
            }
        ],
    }

    output = format_evidence(document)

    assert "Evidence Package ID: evp1_safe" in output
    assert "Retrieval Bundle digest" in output
    assert "Source" in output
    assert "\x1b" not in output
    assert secret_path not in output
    assert "payload" not in output.lower()


def test_outcome_never_prints_idempotency_key_or_media_payload_path(tmp_path: Path) -> None:
    key = "33333333-3333-4333-8333-333333333333"
    private_path = tmp_path / "private-recording.wav"
    private_path.write_bytes(b"private bytes")
    observation = EdgeObservation(
        modality=SCENARIOS["audio_replay"].modality,
        input_label=SCENARIOS["audio_replay"].input_label,
        asset_path=private_path,
        content_type="audio/wav",
    )
    receipt = SubmissionReceipt(201, REPORT_ID, False, key, {"report_id": REPORT_ID})
    outcome = ScenarioOutcome("audio_replay", observation, receipt)

    output = format_outcome(outcome)

    assert key not in output
    assert str(private_path) not in output
    assert "private bytes" not in output
    assert "value not displayed" in output
