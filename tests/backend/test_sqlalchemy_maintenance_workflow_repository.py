from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import ai_core.model_capabilities as model_capabilities
from ai_core.model_capabilities import ModelCapability, ModelLifecycleStatus
from backend.app.db.models.machine import MachineModel
from backend.app.db.models.maintenance_artifacts import (
    AnalysisModel,
    EvidencePackageModel,
    MaintenanceReportModel,
    RetrievalBundleModel,
)
from backend.app.db.session import async_session_factory, engine
from backend.app.persistence.errors import (
    ArtifactIdentityConflictError,
    ArtifactPersistenceIntegrityError,
)
from backend.app.repositories.sqlalchemy_maintenance_workflow_repository import (
    SQLAlchemyMaintenanceWorkflowRepository,
)
from backend.app.services.maintenance_workflow_persistence_service import (
    MaintenanceWorkflowPersistenceService,
)
from domain.entities.prediction import Prediction
from domain.enums.modality import Modality
from inference.result import InferenceResult
from modules.copilot.service import MaintenanceCopilotService
from modules.retriever.retriever import KnowledgeRetriever
from tests.backend.maintenance_persistence_support import (
    make_vision_workflow_result,
    replace_report,
)


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
    await engine.dispose()


async def _insert_machine(
    session: AsyncSession,
    machine_id: UUID,
    name: str,
    asset_type: str,
) -> None:
    session.add(MachineModel(id=machine_id, name=name, asset_type=asset_type))
    await session.flush()


@pytest.mark.asyncio
async def test_persist_and_load_complete_verified_chain_from_postgresql(
    db_session: AsyncSession,
) -> None:
    machine, result = make_vision_workflow_result(generated=True)
    await _insert_machine(db_session, machine.id, machine.name, machine.asset_type)
    service = MaintenanceWorkflowPersistenceService(
        SQLAlchemyMaintenanceWorkflowRepository(db_session)
    )

    reference = await service.persist(result)
    db_session.expunge_all()
    historical = await service.get_by_report_id(reference.maintenance_report_id)

    assert historical is not None
    assert historical.machine == machine
    assert historical.analysis == result.analysis
    assert historical.evidence_package == result.evidence_package
    assert historical.retrieval_bundle == result.retrieval_bundle
    assert historical.maintenance_report == result.maintenance_report


@pytest.mark.asyncio
async def test_machine_history_uses_generated_time_then_report_id_descending(
    db_session: AsyncSession,
) -> None:
    machine, base = make_vision_workflow_result()
    await _insert_machine(db_session, machine.id, machine.name, machine.asset_type)
    service = MaintenanceWorkflowPersistenceService(
        SQLAlchemyMaintenanceWorkflowRepository(db_session)
    )
    earlier = replace_report(
        base,
        report_id=UUID("00000000-0000-0000-0000-000000000003"),
        generated_at=datetime(2026, 8, 26, 9, 0, tzinfo=UTC),
    )
    tied_lower = replace_report(
        base,
        report_id=UUID("00000000-0000-0000-0000-000000000001"),
        generated_at=datetime(2026, 8, 26, 10, 0, tzinfo=UTC),
    )
    tied_higher = replace_report(
        base,
        report_id=UUID("00000000-0000-0000-0000-000000000002"),
        generated_at=datetime(2026, 8, 26, 10, 0, tzinfo=UTC),
    )
    for workflow in (earlier, tied_lower, tied_higher):
        await service.persist(workflow)
    db_session.expunge_all()

    history = await service.list_for_machine(machine.id)

    assert [item.maintenance_report.report_id for item in history] == [
        tied_higher.maintenance_report.report_id,
        tied_lower.maintenance_report.report_id,
        earlier.maintenance_report.report_id,
    ]


@pytest.mark.asyncio
async def test_exact_duplicate_workflow_replay_reuses_all_four_rows(
    db_session: AsyncSession,
) -> None:
    machine, result = make_vision_workflow_result()
    await _insert_machine(db_session, machine.id, machine.name, machine.asset_type)
    service = MaintenanceWorkflowPersistenceService(
        SQLAlchemyMaintenanceWorkflowRepository(db_session)
    )

    first = await service.persist(result)
    db_session.expunge_all()
    second = await service.persist(result)

    assert second == first
    assert await db_session.get(AnalysisModel, result.analysis.id) is not None
    assert (
        await db_session.get(EvidencePackageModel, result.evidence_package.package_id) is not None
    )
    assert (
        await db_session.get(
            RetrievalBundleModel,
            result.retrieval_bundle.retrieval_bundle_digest_sha256,
        )
        is not None
    )
    assert (
        await db_session.get(MaintenanceReportModel, result.maintenance_report.report_id)
        is not None
    )


@pytest.mark.asyncio
async def test_same_evidence_identity_with_different_payload_fails_without_overwrite(
    db_session: AsyncSession,
) -> None:
    machine, result = make_vision_workflow_result()
    await _insert_machine(db_session, machine.id, machine.name, machine.asset_type)
    repository = SQLAlchemyMaintenanceWorkflowRepository(db_session)
    service = MaintenanceWorkflowPersistenceService(repository)
    await service.persist(result)
    stored = await db_session.get(
        EvidencePackageModel,
        result.evidence_package.package_id,
    )
    assert stored is not None
    conflicting_payload = dict(stored.payload)
    conflicting_payload["unexpected"] = "conflicting immutable content"
    stored.payload = conflicting_payload
    await db_session.flush()

    with pytest.raises(ArtifactIdentityConflictError, match="different content"):
        await repository.save_evidence_package(result.evidence_package)

    assert stored.payload == conflicting_payload


@pytest.mark.asyncio
async def test_same_report_identity_with_different_payload_fails_without_overwrite(
    db_session: AsyncSession,
) -> None:
    machine, result = make_vision_workflow_result()
    await _insert_machine(db_session, machine.id, machine.name, machine.asset_type)
    repository = SQLAlchemyMaintenanceWorkflowRepository(db_session)
    service = MaintenanceWorkflowPersistenceService(repository)
    await service.persist(result)
    stored = await db_session.get(
        MaintenanceReportModel,
        result.maintenance_report.report_id,
    )
    assert stored is not None
    conflicting_payload = dict(stored.payload)
    conflicting_payload["unexpected"] = "conflicting immutable content"
    stored.payload = conflicting_payload
    await db_session.flush()

    with pytest.raises(ArtifactIdentityConflictError, match="different content"):
        await repository.save_maintenance_report(result.maintenance_report)

    assert stored.payload == conflicting_payload


class _FailAfterReportFlushRepository(SQLAlchemyMaintenanceWorkflowRepository):
    async def save_maintenance_report(self, report: object) -> None:
        await super().save_maintenance_report(report)  # type: ignore[arg-type]
        raise RuntimeError("Synthetic failure after Maintenance Report flush")


@pytest.mark.asyncio
async def test_outer_transaction_rollback_removes_all_four_staged_artifacts(
    db_session: AsyncSession,
) -> None:
    machine, result = make_vision_workflow_result()
    await _insert_machine(db_session, machine.id, machine.name, machine.asset_type)
    service = MaintenanceWorkflowPersistenceService(_FailAfterReportFlushRepository(db_session))

    with pytest.raises(RuntimeError, match="Synthetic failure"):
        await service.persist(result)
    await db_session.rollback()

    assert await db_session.get(AnalysisModel, result.analysis.id) is None
    assert await db_session.get(EvidencePackageModel, result.evidence_package.package_id) is None
    assert (
        await db_session.get(
            RetrievalBundleModel,
            result.retrieval_bundle.retrieval_bundle_digest_sha256,
        )
        is None
    )
    assert await db_session.get(MaintenanceReportModel, result.maintenance_report.report_id) is None


@pytest.mark.parametrize(
    ("model_type", "identity_attribute", "payload_field", "tampered_value"),
    [
        pytest.param(
            AnalysisModel,
            "id",
            "status",
            "invalid-analysis-status",
            id="analysis",
        ),
        pytest.param(
            EvidencePackageModel,
            "package_id",
            "package_digest_sha256",
            "0" * 64,
            id="evidence-package",
        ),
        pytest.param(
            RetrievalBundleModel,
            "retrieval_bundle_digest_sha256",
            "retrieval_bundle_digest_sha256",
            "0" * 64,
            id="retrieval-bundle",
        ),
        pytest.param(
            MaintenanceReportModel,
            "report_id",
            "report_digest_sha256",
            "0" * 64,
            id="maintenance-report",
        ),
    ],
)
@pytest.mark.asyncio
async def test_historical_load_fails_closed_for_tampered_jsonb_payload(
    db_session: AsyncSession,
    model_type: type[AnalysisModel]
    | type[EvidencePackageModel]
    | type[RetrievalBundleModel]
    | type[MaintenanceReportModel],
    identity_attribute: str,
    payload_field: str,
    tampered_value: str,
) -> None:
    machine, result = make_vision_workflow_result()
    await _insert_machine(db_session, machine.id, machine.name, machine.asset_type)
    service = MaintenanceWorkflowPersistenceService(
        SQLAlchemyMaintenanceWorkflowRepository(db_session)
    )
    await service.persist(result)
    artifact = {
        AnalysisModel: result.analysis,
        EvidencePackageModel: result.evidence_package,
        RetrievalBundleModel: result.retrieval_bundle,
        MaintenanceReportModel: result.maintenance_report,
    }[model_type]
    stored = await db_session.get(model_type, getattr(artifact, identity_attribute))
    assert stored is not None
    tampered_payload = dict(stored.payload)
    tampered_payload[payload_field] = tampered_value
    stored.payload = tampered_payload
    await db_session.flush()

    with pytest.raises(ArtifactPersistenceIntegrityError):
        await service.get_by_report_id(result.maintenance_report.report_id)


@pytest.mark.asyncio
async def test_provider_unavailable_fallback_report_uses_same_artifact_table(
    db_session: AsyncSession,
) -> None:
    machine, result = make_vision_workflow_result(fallback=True)
    await _insert_machine(db_session, machine.id, machine.name, machine.asset_type)
    service = MaintenanceWorkflowPersistenceService(
        SQLAlchemyMaintenanceWorkflowRepository(db_session)
    )

    await service.persist(result)
    db_session.expunge_all()
    historical = await service.get_by_report_id(result.maintenance_report.report_id)

    assert historical is not None
    assert historical.maintenance_report.generation_status.value == "fallback"
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MaintenanceReportModel)
            .where(MaintenanceReportModel.report_id == result.maintenance_report.report_id)
        )
        == 1
    )


@pytest.mark.asyncio
async def test_machine_delete_is_restricted_while_history_exists(
    db_session: AsyncSession,
) -> None:
    machine, result = make_vision_workflow_result()
    await _insert_machine(db_session, machine.id, machine.name, machine.asset_type)
    service = MaintenanceWorkflowPersistenceService(
        SQLAlchemyMaintenanceWorkflowRepository(db_session)
    )
    await service.persist(result)
    stored_machine = await db_session.get(MachineModel, machine.id)
    assert stored_machine is not None

    await db_session.delete(stored_machine)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_history_retains_old_model_when_current_default_changes(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    machine, result = make_vision_workflow_result()
    assert result.evidence_package.models[0].model_id == "vision_visa_pcb1_v1"
    await _insert_machine(db_session, machine.id, machine.name, machine.asset_type)
    service = MaintenanceWorkflowPersistenceService(
        SQLAlchemyMaintenanceWorkflowRepository(db_session)
    )
    await service.persist(result)
    fake_default = ModelCapability(
        model_id="vision_fake_v2",
        modality=Modality.VISION,
        status=ModelLifecycleStatus.EXPERIMENTAL,
        runtime_default=True,
        validated_scope="Synthetic persistence default-change regression only",
        evaluation_reference="evaluation/vision_baseline_results.json",
        confidence_semantics="synthetic_test_confidence",
    )
    monkeypatch.setattr(
        model_capabilities,
        "get_runtime_default_capability",
        lambda modality: fake_default,
    )
    db_session.expunge_all()

    historical = await service.get_by_report_id(result.maintenance_report.report_id)

    assert historical is not None
    assert historical.evidence_package.models[0].model_id == "vision_visa_pcb1_v1"
    assert historical.maintenance_report.producing_models[0].model_id == ("vision_visa_pcb1_v1")
    assert "vision_fake_v2" not in repr(historical)


@pytest.mark.asyncio
async def test_generated_history_does_not_rerun_retrieval_or_copilot(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    machine, result = make_vision_workflow_result(generated=True)
    await _insert_machine(db_session, machine.id, machine.name, machine.asset_type)
    service = MaintenanceWorkflowPersistenceService(
        SQLAlchemyMaintenanceWorkflowRepository(db_session)
    )
    await service.persist(result)
    calls = {"retrieval": 0, "copilot": 0}

    def unexpected_retrieval(*args: object, **kwargs: object) -> object:
        calls["retrieval"] += 1
        raise AssertionError("Historical reads must not rerun retrieval")

    async def unexpected_copilot(*args: object, **kwargs: object) -> object:
        calls["copilot"] += 1
        raise AssertionError("Historical reads must not rerun Copilot generation")

    monkeypatch.setattr(KnowledgeRetriever, "retrieve", unexpected_retrieval)
    monkeypatch.setattr(MaintenanceCopilotService, "generate_report", unexpected_copilot)
    db_session.expunge_all()

    historical = await service.get_by_report_id(result.maintenance_report.report_id)

    assert historical is not None
    assert historical.retrieval_bundle == result.retrieval_bundle
    assert historical.maintenance_report == result.maintenance_report
    assert historical.maintenance_report.generation_status.value == "generated"
    assert calls == {"retrieval": 0, "copilot": 0}


class _RecordingRepository:
    def __init__(self) -> None:
        self.saved: list[str] = []

    async def save_analysis(self, analysis: object) -> None:
        self.saved.append("analysis")

    async def save_evidence_package(self, package: object) -> None:
        self.saved.append("evidence")

    async def save_retrieval_bundle(self, bundle: object) -> None:
        self.saved.append("retrieval")

    async def save_maintenance_report(self, report: object) -> None:
        self.saved.append("report")

    async def get_by_report_id(self, report_id: UUID) -> None:
        return None

    async def list_for_machine(self, machine_id: UUID) -> list[object]:
        return []


@pytest.mark.asyncio
async def test_mismatched_workflow_is_rejected_before_any_repository_write() -> None:
    _, result = make_vision_workflow_result()
    repository = _RecordingRepository()
    service = MaintenanceWorkflowPersistenceService(repository)  # type: ignore[arg-type]
    mismatched = replace(
        result,
        inference_result=InferenceResult(
            Prediction(Modality.VISION, "healthy", 0.99),
            result.inference_result.producing_model,
        ),
    )

    with pytest.raises(ArtifactPersistenceIntegrityError, match="exact inference"):
        await service.persist(mismatched)

    assert repository.saved == []
