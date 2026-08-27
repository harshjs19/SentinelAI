import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from backend.app.db.models.machine import MachineModel
from backend.app.db.models.maintenance_artifacts import (
    AnalysisModel,
    EvidencePackageModel,
    MaintenanceReportModel,
    RetrievalBundleModel,
)
from backend.app.db.models.maintenance_request import MaintenanceReportRequestModel
from backend.app.db.session import async_session_factory, engine
from backend.app.dependencies import get_maintenance_workflow_service
from backend.app.main import app
from backend.app.services.maintenance_workflow_service import (
    MaintenanceWorkflowRequest,
    MaintenanceWorkflowResult,
)
from domain.entities.machine import Machine
from domain.enums.modality import Modality
from tests.backend.maintenance_persistence_support import make_vision_workflow_result
from tests.backend.test_maintenance_workflow_service import (
    RecordingInferenceService,
    _workflow_service,
)
from tests.copilot.support import FakeMaintenanceGenerator


@dataclass
class CapturingWorkflowService:
    delegate: object
    calls: list[MaintenanceWorkflowRequest] = field(default_factory=list)
    results: list[MaintenanceWorkflowResult] = field(default_factory=list)

    async def execute(
        self,
        request: MaintenanceWorkflowRequest,
    ) -> MaintenanceWorkflowResult:
        self.calls.append(request)
        result = await self.delegate.execute(request)  # type: ignore[attr-defined]
        self.results.append(result)
        return result


class FixedWorkflowService:
    def __init__(self, result: MaintenanceWorkflowResult) -> None:
        self.result = result
        self.calls: list[MaintenanceWorkflowRequest] = []

    async def execute(
        self,
        request: MaintenanceWorkflowRequest,
    ) -> MaintenanceWorkflowResult:
        self.calls.append(request)
        return self.result


class BlockingWorkflowService(FixedWorkflowService):
    def __init__(self, result: MaintenanceWorkflowResult) -> None:
        super().__init__(result)
        self.started = asyncio.Event()
        self.proceed = asyncio.Event()

    async def execute(
        self,
        request: MaintenanceWorkflowRequest,
    ) -> MaintenanceWorkflowResult:
        self.calls.append(request)
        self.started.set()
        await self.proceed.wait()
        return self.result


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def database_cleanup() -> AsyncIterator[list[Machine]]:
    machines: list[Machine] = []
    yield machines
    async with async_session_factory.begin() as session:
        for machine in reversed(machines):
            report_ids = list(
                await session.scalars(
                    select(MaintenanceReportModel.report_id).where(
                        MaintenanceReportModel.machine_id == machine.id
                    )
                )
            )
            evidence_ids = list(
                await session.scalars(
                    select(EvidencePackageModel.package_id).where(
                        EvidencePackageModel.machine_id == machine.id
                    )
                )
            )
            analysis_ids = list(
                await session.scalars(
                    select(AnalysisModel.id).where(AnalysisModel.machine_id == machine.id)
                )
            )
            retrieval_ids = list(
                await session.scalars(
                    select(RetrievalBundleModel.retrieval_bundle_digest_sha256).where(
                        RetrievalBundleModel.evidence_package_id.in_(evidence_ids)
                    )
                )
            )
            await session.execute(
                delete(MaintenanceReportRequestModel).where(
                    MaintenanceReportRequestModel.machine_id == machine.id
                )
            )
            if report_ids:
                await session.execute(
                    delete(MaintenanceReportModel).where(
                        MaintenanceReportModel.report_id.in_(report_ids)
                    )
                )
            if retrieval_ids:
                await session.execute(
                    delete(RetrievalBundleModel).where(
                        RetrievalBundleModel.retrieval_bundle_digest_sha256.in_(retrieval_ids)
                    )
                )
            if evidence_ids:
                await session.execute(
                    delete(EvidencePackageModel).where(
                        EvidencePackageModel.package_id.in_(evidence_ids)
                    )
                )
            if analysis_ids:
                await session.execute(
                    delete(AnalysisModel).where(AnalysisModel.id.in_(analysis_ids))
                )
            await session.execute(delete(MachineModel).where(MachineModel.id == machine.id))
    await engine.dispose()


async def _insert_machine(machine: Machine) -> None:
    async with async_session_factory.begin() as session:
        session.add(
            MachineModel(
                id=machine.id,
                name=machine.name,
                asset_type=machine.asset_type,
            )
        )


async def _vision_post(
    client: httpx.AsyncClient,
    machine: Machine,
    key: str,
    *,
    content: bytes = b"\x89PNG\r\n\x1a\nexact API bytes",
    intent: str = "explain_finding",
    question: str | None = None,
) -> httpx.Response:
    data = {"intent": intent}
    if question is not None:
        data["question"] = question
    return await client.post(
        f"/machines/{machine.id}/maintenance-reports/vision",
        headers={"Idempotency-Key": key},
        files={"file": ("source.png", content, "image/png")},
        data=data,
    )


@pytest.mark.asyncio
async def test_api_exact_replay_and_conflict_use_real_durable_persistence(
    api_client: httpx.AsyncClient,
    database_cleanup: list[Machine],
) -> None:
    machine, workflow_result = make_vision_workflow_result()
    database_cleanup.append(machine)
    await _insert_machine(machine)
    workflow = FixedWorkflowService(workflow_result)
    app.dependency_overrides[get_maintenance_workflow_service] = lambda: workflow
    key = f"api-replay-{uuid4()}"

    first = await _vision_post(api_client, machine, key)
    replay = await _vision_post(api_client, machine, key)
    conflict = await _vision_post(
        api_client,
        machine,
        key,
        content=b"\x89PNG\r\n\x1a\ndifferent API bytes",
    )

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.headers["Idempotent-Replay"] == "true"
    assert first.json()["report_id"] == replay.json()["report_id"]
    assert conflict.status_code == 409
    assert len(workflow.calls) == 1

    async with async_session_factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MaintenanceReportRequestModel)
                .where(MaintenanceReportRequestModel.machine_id == machine.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MaintenanceReportModel)
                .where(MaintenanceReportModel.machine_id == machine.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AnalysisModel)
                .where(AnalysisModel.machine_id == machine.id)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_api_concurrent_duplicate_executes_workflow_once(
    api_client: httpx.AsyncClient,
    database_cleanup: list[Machine],
) -> None:
    machine, workflow_result = make_vision_workflow_result()
    database_cleanup.append(machine)
    await _insert_machine(machine)
    workflow = BlockingWorkflowService(workflow_result)
    app.dependency_overrides[get_maintenance_workflow_service] = lambda: workflow
    key = f"api-concurrent-{uuid4()}"

    owner = asyncio.create_task(_vision_post(api_client, machine, key))
    await workflow.started.wait()
    duplicate = await _vision_post(api_client, machine, key)
    workflow.proceed.set()
    completed = await owner

    assert completed.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "An identical maintenance request is already processing"}
    assert len(workflow.calls) == 1


@pytest.mark.parametrize(
    ("mode", "intent", "question", "expected_status", "expected_reason"),
    [
        (
            "deterministic",
            "explain_confidence",
            None,
            "deterministic",
            None,
        ),
        (
            "provider-unavailable",
            "explain_finding",
            None,
            "fallback",
            "generation_unavailable",
        ),
        (
            "high-impact",
            "explain_finding",
            "Should I shut this machine down now?",
            "fallback",
            "unsupported_request",
        ),
    ],
)
@pytest.mark.asyncio
async def test_api_persists_verified_no_provider_copilot_outcomes(
    api_client: httpx.AsyncClient,
    database_cleanup: list[Machine],
    mode: str,
    intent: str,
    question: str | None,
    expected_status: str,
    expected_reason: str | None,
) -> None:
    generator = None if mode == "provider-unavailable" else FakeMaintenanceGenerator()
    machine = Machine(uuid4(), f"{mode} API fixture", "pcb1")
    service = _workflow_service(
        machine=machine,
        inference_services={
            Modality.VISION: RecordingInferenceService(
                Modality.VISION,
                "visual_anomaly",
            )
        },
        generator=generator,
    )
    database_cleanup.append(machine)
    await _insert_machine(machine)
    workflow = CapturingWorkflowService(service)
    app.dependency_overrides[get_maintenance_workflow_service] = lambda: workflow

    response = await _vision_post(
        api_client,
        machine,
        f"api-{mode}-{uuid4()}",
        intent=intent,
        question=question,
    )

    assert response.status_code == 201
    assert response.json()["generation_status"] == expected_status
    assert response.json()["fallback_reason"] == expected_reason
    assert len(workflow.calls) == 1
    assert len(workflow.results) == 1
    if generator is not None:
        assert generator.calls == []
    async with async_session_factory() as session:
        assert (
            await session.get(
                MaintenanceReportModel,
                workflow.results[0].maintenance_report.report_id,
            )
            is not None
        )
