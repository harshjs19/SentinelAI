from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException

from backend.app.dependencies import (
    get_machine_service,
    get_maintenance_report_creation_service,
    get_maintenance_workflow_persistence_service,
)
from backend.app.errors import model_unavailable_error
from backend.app.main import app
from backend.app.persistence.errors import ArtifactPersistenceIntegrityError
from backend.app.repositories.maintenance_workflow_repository import (
    HistoricalMaintenanceWorkflow,
)
from backend.app.services.maintenance_report_creation_service import (
    MaintenanceReportCreationResult,
)
from backend.app.services.maintenance_request_idempotency_service import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    InvalidIdempotencyKeyError,
)
from backend.app.services.maintenance_workflow_service import (
    AudioMaintenanceRequest,
    MaintenanceWorkflowMachineNotFoundError,
    ThermalMaintenanceRequest,
    TimeseriesMaintenanceRequest,
    VisionMaintenanceRequest,
)
from domain.entities.machine import Machine
from modules.copilot.context import CopilotContextBuilder
from modules.copilot.contracts import (
    CopilotIntent,
    FallbackReason,
    MaintenanceCopilotRequest,
)
from modules.copilot.report import assemble_fallback_report
from modules.retriever.exceptions import RetrievalUnavailableError
from tests.backend.maintenance_persistence_support import make_vision_workflow_result


class RecordingCreationService:
    def __init__(
        self,
        result: MaintenanceReportCreationResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[object, str]] = []

    async def create(
        self,
        request: object,
        idempotency_key: str,
    ) -> MaintenanceReportCreationResult:
        self.calls.append((request, idempotency_key))
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("No API creation result configured")
        return self.result


class FakePersistenceService:
    def __init__(
        self,
        historical: list[HistoricalMaintenanceWorkflow] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.historical = historical or []
        self.error = error
        self.get_calls: list[UUID] = []
        self.list_calls: list[tuple[UUID, int, int]] = []

    async def get_by_report_id(
        self,
        report_id: UUID,
    ) -> HistoricalMaintenanceWorkflow | None:
        self.get_calls.append(report_id)
        if self.error is not None:
            raise self.error
        return next(
            (item for item in self.historical if item.maintenance_report.report_id == report_id),
            None,
        )

    async def list_for_machine(
        self,
        machine_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> list[HistoricalMaintenanceWorkflow]:
        self.list_calls.append((machine_id, limit, offset))
        if self.error is not None:
            raise self.error
        matching = [item for item in self.historical if item.machine.id == machine_id]
        return matching[offset : offset + limit]


class FakeMachineService:
    def __init__(self, machine: Machine | None) -> None:
        self.machine = machine

    async def get_machine(self, machine_id: UUID) -> Machine | None:
        if self.machine is not None and self.machine.id == machine_id:
            return self.machine
        return None


def _historical() -> HistoricalMaintenanceWorkflow:
    machine, result = make_vision_workflow_result(generated=True)
    return HistoricalMaintenanceWorkflow(
        machine=machine,
        analysis=result.analysis,
        evidence_package=result.evidence_package,
        retrieval_bundle=result.retrieval_bundle,
        maintenance_report=result.maintenance_report,
    )


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def _timeseries_payload(intent: str = "explain_confidence") -> dict[str, object]:
    sample = {
        "ch1_bias": 0.1,
        "ch1_derivedPk": 0.2,
        "ch1_direct": 0.3,
        "ch1_directRMS": 0.4,
        "ch1_velocityPk": 0.5,
        "ch1_velocityRMS": 0.6,
    }
    return {"samples": [sample, sample], "intent": intent, "question": None}


@pytest.mark.asyncio
async def test_timeseries_post_accepts_only_source_intent_question_and_key(
    api_client: httpx.AsyncClient,
) -> None:
    historical = _historical()
    creation = RecordingCreationService(
        MaintenanceReportCreationResult(
            historical.maintenance_report,
            replayed=False,
        )
    )
    app.dependency_overrides[get_maintenance_report_creation_service] = lambda: creation

    response = await api_client.post(
        f"/machines/{historical.machine.id}/maintenance-reports/timeseries",
        headers={"Idempotency-Key": "timeseries-request-1"},
        json=_timeseries_payload(),
    )

    assert response.status_code == 201
    request, key = creation.calls[0]
    assert isinstance(request, TimeseriesMaintenanceRequest)
    assert key == "timeseries-request-1"
    assert request.intent is CopilotIntent.EXPLAIN_CONFIDENCE
    assert tuple(request.samples)[0]["ch1_bias"] == 0.1
    assert "report_digest_sha256" not in response.json()
    assert "evidence_reference" not in response.json()


@pytest.mark.parametrize(
    ("endpoint", "request_type"),
    [
        ("audio", AudioMaintenanceRequest),
        ("vision", VisionMaintenanceRequest),
        ("thermal", ThermalMaintenanceRequest),
    ],
)
@pytest.mark.asyncio
async def test_media_post_reads_once_and_passes_exact_bytes_to_workflow_request(
    api_client: httpx.AsyncClient,
    endpoint: str,
    request_type: type[AudioMaintenanceRequest]
    | type[VisionMaintenanceRequest]
    | type[ThermalMaintenanceRequest],
) -> None:
    historical = _historical()
    creation = RecordingCreationService(
        MaintenanceReportCreationResult(
            historical.maintenance_report,
            replayed=False,
        )
    )
    app.dependency_overrides[get_maintenance_report_creation_service] = lambda: creation
    content = b"\x89PNG\r\n\x1a\nexact immutable uploaded bytes"

    response = await api_client.post(
        f"/machines/{historical.machine.id}/maintenance-reports/{endpoint}",
        headers={"Idempotency-Key": f"{endpoint}-request-1"},
        files={"file": ("ignored-name.bin", content, "application/octet-stream")},
        data={"intent": "explain_finding", "question": "Explain this finding"},
    )

    assert response.status_code == 201
    request, _ = creation.calls[0]
    assert isinstance(request, request_type)
    assert request.content is content or request.content == content
    assert request.question == "Explain this finding"


@pytest.mark.asyncio
async def test_completed_replay_returns_200_and_safe_header(
    api_client: httpx.AsyncClient,
) -> None:
    historical = _historical()
    creation = RecordingCreationService(
        MaintenanceReportCreationResult(
            historical.maintenance_report,
            replayed=True,
        )
    )
    app.dependency_overrides[get_maintenance_report_creation_service] = lambda: creation

    response = await api_client.post(
        f"/machines/{historical.machine.id}/maintenance-reports/vision",
        headers={"Idempotency-Key": "replay-request"},
        files={"file": ("image.png", b"\x89PNG\r\n\x1a\nbytes", "image/png")},
        data={"intent": "explain_finding"},
    )

    assert response.status_code == 200
    assert response.headers["Idempotent-Replay"] == "true"
    assert response.json()["report_id"] == str(historical.maintenance_report.report_id)


@pytest.mark.asyncio
async def test_post_requires_idempotency_header(api_client: httpx.AsyncClient) -> None:
    response = await api_client.post(
        f"/machines/{uuid4()}/maintenance-reports/timeseries",
        json=_timeseries_payload(),
    )

    assert response.status_code == 422
    assert "idempotency-key" in response.text.lower()


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (
            InvalidIdempotencyKeyError("Idempotency-Key cannot be blank"),
            422,
            "Idempotency-Key cannot be blank",
        ),
        (
            IdempotencyConflictError(),
            409,
            "Idempotency-Key conflicts with a different request",
        ),
        (
            IdempotencyInProgressError(),
            409,
            "An identical maintenance request is already processing",
        ),
        (MaintenanceWorkflowMachineNotFoundError(), 404, "Machine not found"),
        (
            RetrievalUnavailableError(),
            503,
            "Maintenance knowledge retrieval is not available",
        ),
    ],
)
@pytest.mark.asyncio
async def test_post_maps_known_failures_without_internal_details(
    api_client: httpx.AsyncClient,
    error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    creation = RecordingCreationService(error=error)
    app.dependency_overrides[get_maintenance_report_creation_service] = lambda: creation

    response = await api_client.post(
        f"/machines/{uuid4()}/maintenance-reports/timeseries",
        headers={"Idempotency-Key": "safe-error-key"},
        json=_timeseries_payload(),
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (
            ValueError("Maintenance image source must be valid JPEG or PNG bytes"),
            400,
            "Maintenance image source must be valid JPEG or PNG bytes",
        ),
        (
            ArtifactPersistenceIntegrityError("private database detail"),
            500,
            "Maintenance report could not be completed safely",
        ),
    ],
)
@pytest.mark.asyncio
async def test_post_maps_malformed_and_integrity_failures_safely(
    api_client: httpx.AsyncClient,
    error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    creation = RecordingCreationService(error=error)
    app.dependency_overrides[get_maintenance_report_creation_service] = lambda: creation

    response = await api_client.post(
        f"/machines/{uuid4()}/maintenance-reports/timeseries",
        headers={"Idempotency-Key": "safe-error-key"},
        json=_timeseries_payload(),
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert "private database detail" not in response.text


@pytest.mark.asyncio
async def test_post_preserves_existing_safe_missing_model_503(
    api_client: httpx.AsyncClient,
) -> None:
    error: HTTPException = model_unavailable_error("Vision")
    creation = RecordingCreationService(error=error)
    app.dependency_overrides[get_maintenance_report_creation_service] = lambda: creation

    response = await api_client.post(
        f"/machines/{uuid4()}/maintenance-reports/vision",
        headers={"Idempotency-Key": "missing-model-key"},
        files={"file": ("image.png", b"\x89PNG\r\n\x1a\nbytes", "image/png")},
        data={"intent": "explain_finding"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Vision model is not available"}
    assert "path" not in response.text.lower()


@pytest.mark.asyncio
async def test_historical_get_returns_stored_safe_report_without_workflow_dependency(
    api_client: httpx.AsyncClient,
) -> None:
    historical = _historical()
    persistence = FakePersistenceService([historical])
    app.dependency_overrides[get_maintenance_workflow_persistence_service] = lambda: persistence

    response = await api_client.get(
        f"/maintenance-reports/{historical.maintenance_report.report_id}"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["producing_models"][0]["model_id"] == "vision_visa_pcb1_v1"
    assert body["citations"][0]["citation_id"] == "K1"
    assert "chunk_id" not in body["citations"][0]
    assert "source_digest_sha256" not in body["citations"][0]
    assert persistence.get_calls == [historical.maintenance_report.report_id]


@pytest.mark.asyncio
async def test_historical_evidence_get_returns_only_typed_lineage_metadata(
    api_client: httpx.AsyncClient,
) -> None:
    historical = _historical()
    persistence = FakePersistenceService([historical])
    app.dependency_overrides[get_maintenance_workflow_persistence_service] = lambda: persistence

    response = await api_client.get(
        f"/maintenance-reports/{historical.maintenance_report.report_id}/evidence"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis"]["analysis_id"] == str(historical.analysis.id)
    assert body["evidence_package"]["package_id"] == (historical.evidence_package.package_id)
    assert body["retrieval_bundle"]["retrieval_bundle_digest_sha256"] == (
        historical.retrieval_bundle.retrieval_bundle_digest_sha256
    )
    assert body["report"]["report_id"] == str(historical.maintenance_report.report_id)
    assert body["sources"] == [
        {
            "modality": source.modality.value,
            "source_kind": source.source_kind.value,
            "sha256": source.sha256,
            "size_bytes": source.size_bytes,
            "content_type": source.content_type,
        }
        for source in historical.evidence_package.sources
    ]
    assert "chunks" not in response.text
    assert "queries" not in response.text
    assert "source_uri" not in response.text
    assert "collection_name" not in response.text


@pytest.mark.asyncio
async def test_historical_get_returns_404_or_safe_integrity_error(
    api_client: httpx.AsyncClient,
) -> None:
    persistence = FakePersistenceService()
    app.dependency_overrides[get_maintenance_workflow_persistence_service] = lambda: persistence
    report_id = uuid4()

    missing = await api_client.get(f"/maintenance-reports/{report_id}")
    missing_evidence = await api_client.get(f"/maintenance-reports/{report_id}/evidence")
    persistence.error = ArtifactPersistenceIntegrityError("private database detail")
    corrupt = await api_client.get(f"/maintenance-reports/{report_id}/evidence")

    assert missing.status_code == 404
    assert missing_evidence.status_code == 404
    assert missing_evidence.json() == {"detail": "Maintenance report not found"}
    assert corrupt.status_code == 500
    assert corrupt.json() == {"detail": "Stored maintenance report failed integrity verification"}
    assert "private" not in corrupt.text


@pytest.mark.asyncio
async def test_machine_history_checks_machine_and_forwards_bounded_pagination(
    api_client: httpx.AsyncClient,
) -> None:
    historical = _historical()
    persistence = FakePersistenceService([historical, historical, historical])
    app.dependency_overrides[get_maintenance_workflow_persistence_service] = lambda: persistence
    app.dependency_overrides[get_machine_service] = lambda: FakeMachineService(historical.machine)

    response = await api_client.get(
        f"/machines/{historical.machine.id}/maintenance-reports?limit=1&offset=1"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert set(response.json()[0]) == {
        "report_id",
        "machine_id",
        "generated_at",
        "generation_status",
        "condition",
        "analysis_status",
        "executive_summary",
    }
    assert persistence.list_calls == [(historical.machine.id, 1, 1)]


@pytest.mark.asyncio
async def test_machine_history_unknown_machine_returns_404_without_history_query(
    api_client: httpx.AsyncClient,
) -> None:
    persistence = FakePersistenceService()
    app.dependency_overrides[get_maintenance_workflow_persistence_service] = lambda: persistence
    app.dependency_overrides[get_machine_service] = lambda: FakeMachineService(None)

    response = await api_client.get(f"/machines/{uuid4()}/maintenance-reports")

    assert response.status_code == 404
    assert persistence.list_calls == []


@pytest.mark.parametrize(
    "query",
    ["limit=0", "limit=101", "offset=-1"],
)
@pytest.mark.asyncio
async def test_machine_history_rejects_unbounded_pagination(
    api_client: httpx.AsyncClient,
    query: str,
) -> None:
    response = await api_client.get(f"/machines/{uuid4()}/maintenance-reports?{query}")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_high_impact_question_is_passed_to_safe_server_workflow_contract(
    api_client: httpx.AsyncClient,
) -> None:
    historical = _historical()
    prepared = CopilotContextBuilder().build(
        MaintenanceCopilotRequest(
            evidence_package=historical.evidence_package,
            retrieval_bundle=historical.retrieval_bundle,
            intent=CopilotIntent.EXPLAIN_FINDING,
            question="Should I shut this machine down now?",
        )
    )
    report = assemble_fallback_report(
        prepared,
        FallbackReason.UNSUPPORTED_REQUEST,
    )
    creation = RecordingCreationService(MaintenanceReportCreationResult(report, replayed=False))
    app.dependency_overrides[get_maintenance_report_creation_service] = lambda: creation

    response = await api_client.post(
        f"/machines/{historical.machine.id}/maintenance-reports/vision",
        headers={"Idempotency-Key": "high-impact-request"},
        files={"file": ("image.png", b"\x89PNG\r\n\x1a\nbytes", "image/png")},
        data={
            "intent": "explain_finding",
            "question": "Should I shut this machine down now?",
        },
    )

    assert response.status_code == 201
    assert response.json()["fallback_reason"] == "unsupported_request"
    request, _ = creation.calls[0]
    assert isinstance(request, VisionMaintenanceRequest)
    assert request.question == "Should I shut this machine down now?"


@pytest.mark.parametrize(
    ("fallback", "expected_status", "expected_reason"),
    [
        (False, "deterministic", None),
        (True, "fallback", "generation_unavailable"),
    ],
)
@pytest.mark.asyncio
async def test_no_provider_deterministic_and_fallback_reports_return_through_api(
    api_client: httpx.AsyncClient,
    fallback: bool,
    expected_status: str,
    expected_reason: str | None,
) -> None:
    _, result = make_vision_workflow_result(fallback=fallback)
    creation = RecordingCreationService(
        MaintenanceReportCreationResult(result.maintenance_report, replayed=False)
    )
    app.dependency_overrides[get_maintenance_report_creation_service] = lambda: creation

    response = await api_client.post(
        f"/machines/{result.maintenance_report.machine.machine_id}/maintenance-reports/vision",
        headers={"Idempotency-Key": f"no-provider-{fallback}"},
        files={"file": ("image.png", b"\x89PNG\r\n\x1a\nbytes", "image/png")},
        data={
            "intent": "explain_finding" if fallback else "explain_confidence",
        },
    )

    assert response.status_code == 201
    assert response.json()["generation_status"] == expected_status
    assert response.json()["fallback_reason"] == expected_reason


def test_post_openapi_schemas_do_not_accept_authoritative_derived_artifacts() -> None:
    schema = app.openapi()
    forbidden = {
        "prediction",
        "analysis",
        "evidence_package",
        "retrieval_bundle",
        "producing_model",
        "report_digest",
    }
    for endpoint in ("timeseries", "audio", "vision", "thermal"):
        operation = schema["paths"][f"/machines/{{machine_id}}/maintenance-reports/{endpoint}"][
            "post"
        ]
        request_content = operation["requestBody"]["content"]
        for media_contract in request_content.values():
            request_schema = media_contract["schema"]
            if "$ref" in request_schema:
                component_name = request_schema["$ref"].rsplit("/", maxsplit=1)[-1]
                request_schema = schema["components"]["schemas"][component_name]
            assert forbidden.isdisjoint(str(request_schema).lower())
