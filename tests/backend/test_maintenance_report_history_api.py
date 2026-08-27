from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

import ai_core.model_capabilities as model_capabilities
import backend.app.dependencies as dependencies
from ai_core.model_capabilities import ModelCapability, ModelLifecycleStatus
from backend.app.db.models.machine import MachineModel
from backend.app.db.models.maintenance_artifacts import EvidencePackageModel
from backend.app.db.session import async_session_factory, engine
from backend.app.dependencies import (
    get_machine_service,
    get_maintenance_workflow_persistence_service,
)
from backend.app.main import app
from backend.app.repositories.sqlalchemy_maintenance_workflow_repository import (
    SQLAlchemyMaintenanceWorkflowRepository,
)
from backend.app.services.maintenance_workflow_persistence_service import (
    MaintenanceWorkflowPersistenceService,
)
from domain.entities.machine import Machine
from domain.enums.modality import Modality
from tests.backend.maintenance_persistence_support import (
    make_vision_workflow_result,
    replace_report,
)


class ExistingMachineService:
    def __init__(self, machine: Machine) -> None:
        self._machine = machine

    async def get_machine(self, machine_id: UUID) -> Machine | None:
        return self._machine if self._machine.id == machine_id else None


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _insert_machine(session: AsyncSession, machine: Machine) -> None:
    session.add(
        MachineModel(
            id=machine.id,
            name=machine.name,
            asset_type=machine.asset_type,
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_historical_get_uses_only_verified_stored_chain(
    db_session: AsyncSession,
    api_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    machine, result = make_vision_workflow_result(generated=True)
    await _insert_machine(db_session, machine)
    persistence = MaintenanceWorkflowPersistenceService(
        SQLAlchemyMaintenanceWorkflowRepository(db_session)
    )
    await persistence.persist(result)
    db_session.expunge_all()
    calls = {"predictor": 0, "retriever": 0, "generator": 0, "default": 0}

    def unavailable(name: str) -> object:
        calls[name] += 1
        raise AssertionError(f"Historical GET reran {name}")

    monkeypatch.setattr(
        dependencies,
        "get_vision_inference_service",
        lambda: unavailable("predictor"),
    )
    monkeypatch.setattr(
        dependencies,
        "get_knowledge_retriever",
        lambda: unavailable("retriever"),
    )
    monkeypatch.setattr(
        dependencies,
        "get_maintenance_copilot_service",
        lambda: unavailable("generator"),
    )
    fake_default = ModelCapability(
        model_id="vision_fake_v2",
        modality=Modality.VISION,
        status=ModelLifecycleStatus.EXPERIMENTAL,
        runtime_default=True,
        validated_scope="Synthetic historical API regression",
        evaluation_reference="evaluation/vision_baseline_results.json",
        confidence_semantics="synthetic_test_confidence",
    )

    def changed_default(modality: Modality) -> ModelCapability:
        calls["default"] += 1
        return fake_default

    monkeypatch.setattr(
        model_capabilities,
        "get_runtime_default_capability",
        changed_default,
    )
    app.dependency_overrides[get_maintenance_workflow_persistence_service] = lambda: persistence

    response = await api_client.get(f"/maintenance-reports/{result.maintenance_report.report_id}")

    assert response.status_code == 200
    assert response.json()["producing_models"][0]["model_id"] == "vision_visa_pcb1_v1"
    assert response.json()["citations"][0]["citation_id"] == "K1"
    assert calls == {"predictor": 0, "retriever": 0, "generator": 0, "default": 0}


@pytest.mark.asyncio
async def test_tampered_historical_chain_fails_closed_at_api_boundary(
    db_session: AsyncSession,
    api_client: httpx.AsyncClient,
) -> None:
    machine, result = make_vision_workflow_result()
    await _insert_machine(db_session, machine)
    persistence = MaintenanceWorkflowPersistenceService(
        SQLAlchemyMaintenanceWorkflowRepository(db_session)
    )
    await persistence.persist(result)
    stored = await db_session.get(
        EvidencePackageModel,
        result.evidence_package.package_id,
    )
    assert stored is not None
    tampered = dict(stored.payload)
    tampered["package_digest_sha256"] = "0" * 64
    stored.payload = tampered
    await db_session.flush()
    db_session.expunge_all()
    app.dependency_overrides[get_maintenance_workflow_persistence_service] = lambda: persistence

    response = await api_client.get(f"/maintenance-reports/{result.maintenance_report.report_id}")

    assert response.status_code == 500
    assert response.json() == {"detail": "Stored maintenance report failed integrity verification"}
    assert "digest" not in response.text.lower()


@pytest.mark.asyncio
async def test_machine_history_pagination_preserves_deterministic_order_across_pages(
    db_session: AsyncSession,
    api_client: httpx.AsyncClient,
) -> None:
    machine, base = make_vision_workflow_result()
    await _insert_machine(db_session, machine)
    persistence = MaintenanceWorkflowPersistenceService(
        SQLAlchemyMaintenanceWorkflowRepository(db_session)
    )
    earlier = replace_report(
        base,
        report_id=UUID("00000000-0000-0000-0000-000000000103"),
        generated_at=datetime(2026, 8, 27, 9, 0, tzinfo=UTC),
    )
    tied_lower = replace_report(
        base,
        report_id=UUID("00000000-0000-0000-0000-000000000101"),
        generated_at=datetime(2026, 8, 27, 10, 0, tzinfo=UTC),
    )
    tied_higher = replace_report(
        base,
        report_id=UUID("00000000-0000-0000-0000-000000000102"),
        generated_at=datetime(2026, 8, 27, 10, 0, tzinfo=UTC),
    )
    for workflow in (earlier, tied_lower, tied_higher):
        await persistence.persist(workflow)
    db_session.expunge_all()
    app.dependency_overrides[get_maintenance_workflow_persistence_service] = lambda: persistence
    app.dependency_overrides[get_machine_service] = lambda: ExistingMachineService(machine)

    first_page = await api_client.get(
        f"/machines/{machine.id}/maintenance-reports?limit=2&offset=0"
    )
    second_page = await api_client.get(
        f"/machines/{machine.id}/maintenance-reports?limit=2&offset=2"
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert [item["report_id"] for item in first_page.json()] == [
        str(tied_higher.maintenance_report.report_id),
        str(tied_lower.maintenance_report.report_id),
    ]
    assert [item["report_id"] for item in second_page.json()] == [
        str(earlier.maintenance_report.report_id)
    ]
