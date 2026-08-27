import asyncio
import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.machine import MachineModel
from backend.app.db.models.maintenance_artifacts import (
    AnalysisModel,
    EvidencePackageModel,
    MaintenanceReportModel,
    RetrievalBundleModel,
)
from backend.app.db.models.maintenance_request import MaintenanceReportRequestModel
from backend.app.db.session import async_session_factory, engine
from backend.app.repositories.maintenance_request_idempotency_repository import (
    MaintenanceRequestStatus,
)
from backend.app.repositories.sqlalchemy_maintenance_request_idempotency_repository import (
    SQLAlchemyMaintenanceRequestIdempotencyRepository,
)
from backend.app.repositories.sqlalchemy_maintenance_workflow_repository import (
    SQLAlchemyMaintenanceWorkflowRepository,
)
from backend.app.services.maintenance_report_creation_service import (
    MaintenanceReportCreationService,
)
from backend.app.services.maintenance_request_idempotency_service import (
    IdempotencyClaimLostError,
    IdempotencyConflictError,
    IdempotencyInProgressError,
    InvalidIdempotencyKeyError,
    MaintenanceRequestIdempotencyService,
    ReservationDisposition,
    maintenance_request_identity,
    validate_idempotency_key,
)
from backend.app.services.maintenance_workflow_persistence_service import (
    MaintenanceWorkflowPersistenceService,
)
from backend.app.services.maintenance_workflow_service import (
    AudioMaintenanceRequest,
    MaintenanceWorkflowRequest,
    MaintenanceWorkflowResult,
    TimeseriesMaintenanceRequest,
    VisionMaintenanceRequest,
    maintenance_request_source_provenance,
)
from domain.enums.modality import Modality
from modules.copilot.contracts import CopilotIntent
from tests.backend.maintenance_persistence_support import make_vision_workflow_result


class RecordingWorkflowService:
    def __init__(self, result: MaintenanceWorkflowResult) -> None:
        self.result = result
        self.calls: list[MaintenanceWorkflowRequest] = []

    async def execute(
        self,
        request: MaintenanceWorkflowRequest,
    ) -> MaintenanceWorkflowResult:
        self.calls.append(request)
        return self.result


class BlockingWorkflowService(RecordingWorkflowService):
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


class FailingWorkflowService:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, request: MaintenanceWorkflowRequest) -> MaintenanceWorkflowResult:
        self.calls += 1
        raise RuntimeError("Synthetic workflow failure")


class FailAfterPersistService:
    def __init__(self, delegate: MaintenanceWorkflowPersistenceService) -> None:
        self._delegate = delegate

    async def persist(self, result: MaintenanceWorkflowResult) -> object:
        await self._delegate.persist(result)
        raise RuntimeError("Synthetic final transaction failure")


@pytest_asyncio.fixture
async def db_cleanup() -> AsyncIterator[list[tuple[str, object]]]:
    targets: list[tuple[str, object]] = []
    yield targets
    async with async_session_factory.begin() as session:
        for kind, target in reversed(targets):
            if kind == "request":
                await session.execute(
                    delete(MaintenanceReportRequestModel).where(
                        MaintenanceReportRequestModel.idempotency_key_digest == target
                    )
                )
                continue
            machine, result = target
            await session.execute(
                delete(MaintenanceReportRequestModel).where(
                    MaintenanceReportRequestModel.report_id == result.maintenance_report.report_id
                )
            )
            await session.execute(
                delete(MaintenanceReportModel).where(
                    MaintenanceReportModel.report_id == result.maintenance_report.report_id
                )
            )
            await session.execute(
                delete(RetrievalBundleModel).where(
                    RetrievalBundleModel.retrieval_bundle_digest_sha256
                    == result.retrieval_bundle.retrieval_bundle_digest_sha256
                )
            )
            await session.execute(
                delete(EvidencePackageModel).where(
                    EvidencePackageModel.package_id == result.evidence_package.package_id
                )
            )
            await session.execute(
                delete(AnalysisModel).where(AnalysisModel.id == result.analysis.id)
            )
            await session.execute(delete(MachineModel).where(MachineModel.id == machine.id))
    await engine.dispose()


def _vision_request(
    machine_id: UUID, content: bytes = b"\x89PNG\r\n\x1a\nexact bytes"
) -> VisionMaintenanceRequest:
    return VisionMaintenanceRequest(
        machine_id=machine_id,
        content=content,
        intent=CopilotIntent.EXPLAIN_FINDING,
        question="Explain the finding",
    )


def _idempotency_service(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    token: UUID | None = None,
) -> MaintenanceRequestIdempotencyService:
    return MaintenanceRequestIdempotencyService(
        reservation_session_factory=async_session_factory,
        completion_repository=SQLAlchemyMaintenanceRequestIdempotencyRepository(session),
        clock=(lambda: now) if now is not None else None,
        token_factory=(lambda: token) if token is not None else uuid4,
    )


async def _insert_machine(machine: object) -> None:
    async with async_session_factory.begin() as session:
        session.add(
            MachineModel(
                id=machine.id,  # type: ignore[attr-defined]
                name=machine.name,  # type: ignore[attr-defined]
                asset_type=machine.asset_type,  # type: ignore[attr-defined]
            )
        )


async def _create_report(
    workflow: RecordingWorkflowService,
    request: MaintenanceWorkflowRequest,
    key: str,
) -> object:
    async with async_session_factory.begin() as session:
        service = MaintenanceReportCreationService(
            workflow_service=workflow,  # type: ignore[arg-type]
            persistence_service=MaintenanceWorkflowPersistenceService(
                SQLAlchemyMaintenanceWorkflowRepository(session)
            ),
            idempotency_service=_idempotency_service(session),
        )
        return await service.create(request, key)


@pytest.mark.parametrize(
    "key",
    ["", "   ", "contains\ncontrol", "x" * 201],
)
def test_idempotency_key_validation_rejects_unusable_values(key: str) -> None:
    with pytest.raises(InvalidIdempotencyKeyError):
        validate_idempotency_key(key)


def test_request_identity_hashes_opaque_key_and_binds_semantic_request() -> None:
    machine_id = uuid4()
    request = _vision_request(machine_id)

    identity = maintenance_request_identity("opaque-secret-key", request)
    normalized = maintenance_request_identity(
        "opaque-secret-key",
        VisionMaintenanceRequest(
            machine_id=machine_id,
            content=request.content,
            intent=request.intent,
            question="  Explain the finding  ",
        ),
    )
    changed_source = maintenance_request_identity(
        "opaque-secret-key",
        _vision_request(machine_id, b"\x89PNG\r\n\x1a\ndifferent bytes"),
    )
    changed_intent = maintenance_request_identity(
        "opaque-secret-key",
        VisionMaintenanceRequest(
            machine_id=machine_id,
            content=request.content,
            intent=CopilotIntent.EXPLAIN_CONFIDENCE,
            question=request.question,
        ),
    )

    assert identity.idempotency_key_digest == hashlib.sha256(b"opaque-secret-key").hexdigest()
    assert identity.request_digest == normalized.request_digest
    assert identity.request_digest != changed_source.request_digest
    assert identity.request_digest != changed_intent.request_digest
    assert identity.machine_id == machine_id
    assert identity.modality is Modality.VISION
    assert "opaque-secret-key" not in repr(identity)


def test_timeseries_fingerprint_uses_exact_canonical_workflow_snapshot() -> None:
    machine_id = uuid4()
    first = TimeseriesMaintenanceRequest(
        machine_id=machine_id,
        samples=(
            {"ch1_bias": 0.1, "ch1_direct": 0.2},
            {"ch1_bias": 0.3, "ch1_direct": 0.4},
        ),
        intent=CopilotIntent.EXPLAIN_CONFIDENCE,
    )
    equivalent = TimeseriesMaintenanceRequest(
        machine_id=machine_id,
        samples=(
            {"ch1_direct": 0.2, "ch1_bias": 0.1},
            {"ch1_direct": 0.4, "ch1_bias": 0.3},
        ),
        intent=CopilotIntent.EXPLAIN_CONFIDENCE,
    )

    first_source = maintenance_request_source_provenance(first)
    equivalent_source = maintenance_request_source_provenance(equivalent)
    first_identity = maintenance_request_identity("same-key", first)
    equivalent_identity = maintenance_request_identity("same-key", equivalent)

    assert first_source == equivalent_source
    assert first_identity.request_digest == equivalent_identity.request_digest
    assert first_source.content_type == "application/json"


@pytest.mark.asyncio
async def test_database_claim_stores_only_digests_and_request_metadata(
    db_cleanup: list[tuple[str, object]],
) -> None:
    raw_key = f"raw-key-{uuid4()}"
    request = AudioMaintenanceRequest(
        machine_id=uuid4(),
        content=b"RIFF private audio bytes",
        intent=CopilotIntent.EXPLAIN_CONFIDENCE,
    )
    identity = maintenance_request_identity(raw_key, request)
    db_cleanup.append(("request", identity.idempotency_key_digest))
    async with async_session_factory() as session:
        service = _idempotency_service(session)
        reservation = await service.reserve(raw_key, request)
        stored = await session.get(
            MaintenanceReportRequestModel,
            identity.idempotency_key_digest,
        )
        await service.release(reservation)

    assert stored is not None
    assert stored.idempotency_key_digest == hashlib.sha256(raw_key.encode()).hexdigest()
    assert stored.request_digest == identity.request_digest
    assert stored.machine_id == request.machine_id
    assert stored.modality == "audio"
    assert not hasattr(stored, "raw_key")
    assert not hasattr(stored, "source")
    assert raw_key not in repr(stored)
    assert request.content.decode() not in repr(stored)


@pytest.mark.asyncio
async def test_same_key_conflict_and_concurrent_duplicate_use_durable_claim(
    db_cleanup: list[tuple[str, object]],
) -> None:
    key = f"concurrent-{uuid4()}"
    request = _vision_request(uuid4())
    identity = maintenance_request_identity(key, request)
    db_cleanup.append(("request", identity.idempotency_key_digest))
    session_one = async_session_factory()
    session_two = async_session_factory()
    try:
        first_service = _idempotency_service(session_one)
        second_service = _idempotency_service(session_two)
        outcomes = await asyncio.gather(
            first_service.reserve(key, request),
            second_service.reserve(key, request),
            return_exceptions=True,
        )
        reservations = [outcome for outcome in outcomes if not isinstance(outcome, BaseException)]
        errors = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]

        assert len(reservations) == 1
        assert reservations[0].disposition is ReservationDisposition.CLAIMED
        assert len(errors) == 1
        assert isinstance(errors[0], IdempotencyInProgressError)

        with pytest.raises(IdempotencyConflictError):
            await second_service.reserve(
                key,
                _vision_request(request.machine_id, b"\x89PNG\r\n\x1a\nchanged"),
            )
        owner = first_service if outcomes[0] is reservations[0] else second_service
        await owner.release(reservations[0])
    finally:
        await session_one.close()
        await session_two.close()


@pytest.mark.asyncio
async def test_expired_claim_is_reclaimed_and_old_token_cannot_complete(
    db_cleanup: list[tuple[str, object]],
) -> None:
    key = f"stale-{uuid4()}"
    request = _vision_request(uuid4())
    identity = maintenance_request_identity(key, request)
    db_cleanup.append(("request", identity.idempotency_key_digest))
    initial_time = datetime(2026, 8, 27, 10, 0, tzinfo=UTC)
    old_token = uuid4()
    new_token = uuid4()
    async with async_session_factory() as old_session, async_session_factory() as new_session:
        old_service = _idempotency_service(
            old_session,
            now=initial_time,
            token=old_token,
        )
        old_reservation = await old_service.reserve(key, request)
        new_service = _idempotency_service(
            new_session,
            now=initial_time + timedelta(minutes=6),
            token=new_token,
        )
        new_reservation = await new_service.reserve(key, request)

        assert new_reservation.claim_token == new_token
        with pytest.raises(IdempotencyClaimLostError):
            await old_service.complete(old_reservation, uuid4())
        await new_service.release(new_reservation)


@pytest.mark.asyncio
async def test_workflow_failure_releases_owned_claim_for_immediate_retry(
    db_cleanup: list[tuple[str, object]],
) -> None:
    key = f"workflow-failure-{uuid4()}"
    request = _vision_request(uuid4())
    identity = maintenance_request_identity(key, request)
    db_cleanup.append(("request", identity.idempotency_key_digest))
    workflow = FailingWorkflowService()
    async with async_session_factory() as final_session:
        service = MaintenanceReportCreationService(
            workflow_service=workflow,  # type: ignore[arg-type]
            persistence_service=MaintenanceWorkflowPersistenceService(
                SQLAlchemyMaintenanceWorkflowRepository(final_session)
            ),
            idempotency_service=_idempotency_service(final_session),
        )
        with pytest.raises(RuntimeError, match="workflow failure"):
            await service.create(request, key)
        assert (
            await final_session.get(
                MaintenanceReportRequestModel,
                identity.idempotency_key_digest,
            )
            is None
        )
        retry = await _idempotency_service(final_session).reserve(key, request)
        assert retry.disposition is ReservationDisposition.CLAIMED
        await _idempotency_service(final_session).release(retry)


@pytest.mark.asyncio
async def test_completed_request_replays_without_workflow_and_conflict_does_not_execute(
    db_cleanup: list[tuple[str, object]],
) -> None:
    machine, workflow_result = make_vision_workflow_result()
    request = _vision_request(machine.id)
    key = f"replay-{uuid4()}"
    identity = maintenance_request_identity(key, request)
    db_cleanup.extend(
        [
            ("workflow", (machine, workflow_result)),
            ("request", identity.idempotency_key_digest),
        ]
    )
    await _insert_machine(machine)
    workflow = RecordingWorkflowService(workflow_result)

    first = await _create_report(workflow, request, key)
    replay = await _create_report(workflow, request, key)

    assert first.replayed is False  # type: ignore[attr-defined]
    assert replay.replayed is True  # type: ignore[attr-defined]
    assert replay.report == first.report  # type: ignore[attr-defined]
    assert len(workflow.calls) == 1
    with pytest.raises(IdempotencyConflictError):
        await _create_report(
            workflow,
            _vision_request(machine.id, b"\x89PNG\r\n\x1a\nchanged"),
            key,
        )
    assert len(workflow.calls) == 1

    async with async_session_factory() as session:
        stored_request = await session.get(
            MaintenanceReportRequestModel,
            identity.idempotency_key_digest,
        )
        counts = {
            model.__tablename__: await session.scalar(select(func.count()).select_from(model))
            for model in (
                AnalysisModel,
                EvidencePackageModel,
                RetrievalBundleModel,
                MaintenanceReportModel,
            )
        }
    assert stored_request is not None
    assert stored_request.status == MaintenanceRequestStatus.COMPLETED.value
    assert stored_request.report_id == workflow_result.maintenance_report.report_id
    assert all(count >= 1 for count in counts.values())


@pytest.mark.asyncio
async def test_concurrent_creation_executes_workflow_once(
    db_cleanup: list[tuple[str, object]],
) -> None:
    machine, workflow_result = make_vision_workflow_result()
    request = _vision_request(machine.id)
    key = f"creation-concurrent-{uuid4()}"
    identity = maintenance_request_identity(key, request)
    db_cleanup.extend(
        [
            ("workflow", (machine, workflow_result)),
            ("request", identity.idempotency_key_digest),
        ]
    )
    await _insert_machine(machine)
    workflow = BlockingWorkflowService(workflow_result)

    owner_task = asyncio.create_task(_create_report(workflow, request, key))
    await workflow.started.wait()
    with pytest.raises(IdempotencyInProgressError):
        await _create_report(workflow, request, key)
    workflow.proceed.set()
    owner_result = await owner_task

    assert owner_result.replayed is False  # type: ignore[attr-defined]
    assert len(workflow.calls) == 1


@pytest.mark.asyncio
async def test_final_transaction_failure_is_not_completed_and_can_reclaim_after_lease(
    db_cleanup: list[tuple[str, object]],
) -> None:
    machine, workflow_result = make_vision_workflow_result()
    request = _vision_request(machine.id)
    key = f"final-failure-{uuid4()}"
    identity = maintenance_request_identity(key, request)
    db_cleanup.extend(
        [
            ("workflow", (machine, workflow_result)),
            ("request", identity.idempotency_key_digest),
        ]
    )
    await _insert_machine(machine)
    workflow = RecordingWorkflowService(workflow_result)
    initial_time = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)

    async with async_session_factory() as failed_session:
        persistence = MaintenanceWorkflowPersistenceService(
            SQLAlchemyMaintenanceWorkflowRepository(failed_session)
        )
        service = MaintenanceReportCreationService(
            workflow_service=workflow,  # type: ignore[arg-type]
            persistence_service=FailAfterPersistService(persistence),  # type: ignore[arg-type]
            idempotency_service=_idempotency_service(failed_session, now=initial_time),
        )
        with pytest.raises(RuntimeError, match="final transaction failure"):
            await service.create(request, key)
        await failed_session.rollback()

    async with async_session_factory() as session:
        stored = await session.get(
            MaintenanceReportRequestModel,
            identity.idempotency_key_digest,
        )
        assert stored is not None
        assert stored.status == MaintenanceRequestStatus.PROCESSING.value
        assert stored.report_id is None
        assert (
            await session.get(MaintenanceReportModel, workflow_result.maintenance_report.report_id)
            is None
        )
        active_service = _idempotency_service(session, now=initial_time + timedelta(minutes=1))
        with pytest.raises(IdempotencyInProgressError):
            await active_service.reserve(key, request)

    async with async_session_factory.begin() as retry_session:
        retry_service = MaintenanceReportCreationService(
            workflow_service=workflow,  # type: ignore[arg-type]
            persistence_service=MaintenanceWorkflowPersistenceService(
                SQLAlchemyMaintenanceWorkflowRepository(retry_session)
            ),
            idempotency_service=_idempotency_service(
                retry_session,
                now=initial_time + timedelta(minutes=6),
            ),
        )
        retry = await retry_service.create(request, key)

    assert retry.replayed is False
    assert len(workflow.calls) == 2
