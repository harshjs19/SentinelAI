import json
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from edge_simulator.client import (
    ApiConnectionError,
    ApiResponseError,
    ApiTimeoutError,
    SentinelAIClient,
    SimulatorError,
)
from edge_simulator.config import SimulatorConfig
from edge_simulator.models import InputLabel, Modality
from edge_simulator.sources.media import ReplayAudioSource
from edge_simulator.sources.timeseries import SimulatedTimeSeriesSource

MACHINE_ID = "11111111-1111-4111-8111-111111111111"
REPORT_ID = "22222222-2222-4222-8222-222222222222"


def _client(handler: httpx.MockTransport) -> SentinelAIClient:
    return SentinelAIClient(SimulatorConfig(), transport=handler)


def test_health_machine_listing_and_safe_single_machine_selection() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/machines":
            return httpx.Response(
                200,
                json=[{"id": MACHINE_ID, "name": "Pump 1", "asset_type": "bearing"}],
            )
        if request.url.path == f"/machines/{MACHINE_ID}":
            return httpx.Response(
                200,
                json={"id": MACHINE_ID, "name": "Pump 1", "asset_type": "bearing"},
            )
        raise AssertionError(request.url)

    with _client(httpx.MockTransport(handler)) as client:
        assert client.health() == "ok"
        assert client.list_machines()[0].machine_id == MACHINE_ID
        assert client.select_machine(None).name == "Pump 1"
        assert client.select_machine(MACHINE_ID).asset_type == "bearing"


@pytest.mark.parametrize("machine_count", [0, 2])
def test_implicit_machine_selection_stops_unless_exactly_one_exists(machine_count: int) -> None:
    machines = [
        {"id": f"00000000-0000-4000-8000-{index:012d}", "name": str(index), "asset_type": "x"}
        for index in range(1, machine_count + 1)
    ]
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=machines))
    with _client(transport) as client, pytest.raises(SimulatorError):
        client.select_machine(None)


def test_timeseries_submission_uses_exact_public_json_contract_and_fresh_uuid_keys() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"report_id": REPORT_ID})

    observation = SimulatedTimeSeriesSource("healthy", sample_count=2).capture()
    with _client(httpx.MockTransport(handler)) as client:
        first = client.submit_report(MACHINE_ID, observation, intent="summarize_analysis")
        second = client.submit_report(MACHINE_ID, observation, intent="summarize_analysis")

    assert len(requests) == 2
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == f"/machines/{MACHINE_ID}/maintenance-reports/timeseries"
    payload = json.loads(request.content)
    assert set(payload) == {"samples", "intent"}
    assert len(payload["samples"]) == 2
    assert set(payload["samples"][0]) == {
        "ch1_bias",
        "ch1_derivedPk",
        "ch1_direct",
        "ch1_directRMS",
        "ch1_velocityPk",
        "ch1_velocityRMS",
    }
    assert UUID(first.idempotency_key)
    assert UUID(second.idempotency_key)
    assert first.idempotency_key != second.idempotency_key
    assert requests[0].headers["Idempotency-Key"] == first.idempotency_key


def test_media_submission_uses_multipart_without_base64(tmp_path: Path) -> None:
    asset = tmp_path / "bearing.wav"
    asset.write_bytes(b"private recorded bytes")
    observation = ReplayAudioSource(asset).capture()
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(201, json={"report_id": REPORT_ID})

    with _client(httpx.MockTransport(handler)) as client:
        client.submit_report(
            MACHINE_ID,
            observation,
            intent="explain_finding",
            question="Explain the acoustic finding",
        )

    request = captured[0]
    assert request.url.path.endswith("/maintenance-reports/audio")
    assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
    assert b"private recorded bytes" in request.content
    assert b"audio/wav" in request.content
    assert b"explain_finding" in request.content
    assert b"base64" not in request.content


def test_exact_idempotency_key_is_preserved_when_explicitly_replayed() -> None:
    keys: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        keys.append(request.headers["Idempotency-Key"])
        response_number = len(keys)
        return httpx.Response(
            201 if response_number == 1 else 200,
            headers={"Idempotent-Replay": "true"} if response_number == 2 else {},
            json={"report_id": REPORT_ID},
        )

    key = "33333333-3333-4333-8333-333333333333"
    observation = SimulatedTimeSeriesSource("healthy", sample_count=2).capture()
    with _client(httpx.MockTransport(handler)) as client:
        first = client.submit_report(
            MACHINE_ID,
            observation,
            intent="explain_confidence",
            idempotency_key=key,
        )
        replay = client.submit_report(
            MACHINE_ID,
            observation,
            intent="explain_confidence",
            idempotency_key=key,
        )

    assert keys == [key, key]
    assert first.report_id == replay.report_id
    assert replay.replayed


@pytest.mark.parametrize("status_code", [400, 404, 409, 422, 500, 503])
def test_public_api_errors_are_reported_without_response_payload_dump(status_code: int) -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            status_code,
            json={"detail": "bounded public detail", "internal_stack": "private trace"},
        )
    )
    with _client(transport) as client, pytest.raises(ApiResponseError) as captured:
        client.health()
    assert captured.value.status_code == status_code
    assert "bounded public detail" in str(captured.value)
    assert "private trace" not in str(captured.value)
    assert "internal_stack" not in str(captured.value)


@pytest.mark.parametrize(
    ("error_type", "expected_exception"),
    [
        (httpx.ConnectError, ApiConnectionError),
        (httpx.ReadTimeout, ApiTimeoutError),
    ],
)
def test_connectivity_and_timeout_failures_are_friendly_without_retry(
    error_type: type[httpx.RequestError],
    expected_exception: type[SimulatorError],
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise error_type("offline", request=request)

    with _client(httpx.MockTransport(handler)) as client, pytest.raises(expected_exception):
        client.health()
    assert calls == 1


def test_report_evidence_and_history_readbacks_use_only_public_gets() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/evidence"):
            return httpx.Response(200, json={"report": {"report_id": REPORT_ID}})
        if request.url.path == f"/maintenance-reports/{REPORT_ID}":
            return httpx.Response(200, json={"report_id": REPORT_ID})
        return httpx.Response(200, json=[{"report_id": REPORT_ID}])

    with _client(httpx.MockTransport(handler)) as client:
        assert client.get_report(REPORT_ID)["report_id"] == REPORT_ID
        assert client.get_evidence(REPORT_ID)["report"]["report_id"] == REPORT_ID
        assert client.get_history(MACHINE_ID)[0]["report_id"] == REPORT_ID

    assert paths == [
        f"/maintenance-reports/{REPORT_ID}",
        f"/maintenance-reports/{REPORT_ID}/evidence",
        f"/machines/{MACHINE_ID}/maintenance-reports",
    ]


def test_invalid_json_and_invalid_identifiers_fail_locally() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=b"not-json"))
    with _client(transport) as client:
        with pytest.raises(SimulatorError, match="invalid JSON"):
            client.health()
        with pytest.raises(ValueError, match="UUID"):
            client.get_report("not-a-uuid")


def test_observation_contract_remains_single_modality() -> None:
    observation = SimulatedTimeSeriesSource("healthy").capture()
    assert observation.input_label is InputLabel.SIMULATED
    assert observation.modality is Modality.TIMESERIES
    assert observation.asset_path is None
