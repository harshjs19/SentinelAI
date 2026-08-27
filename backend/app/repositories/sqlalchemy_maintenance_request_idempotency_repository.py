from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.maintenance_request import MaintenanceReportRequestModel
from backend.app.repositories.maintenance_request_idempotency_repository import (
    ClaimDisposition,
    MaintenanceRequestClaim,
    MaintenanceRequestIdentity,
    MaintenanceRequestStatus,
)


class IdempotencyPersistenceIntegrityError(RuntimeError):
    pass


class SQLAlchemyMaintenanceRequestIdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(
        self,
        identity: MaintenanceRequestIdentity,
        *,
        claim_token: UUID,
        now: datetime,
        lease_expires_at: datetime,
    ) -> MaintenanceRequestClaim:
        inserted = await self._session.scalar(
            insert(MaintenanceReportRequestModel)
            .values(
                idempotency_key_digest=identity.idempotency_key_digest,
                request_digest=identity.request_digest,
                machine_id=identity.machine_id,
                modality=identity.modality.value,
                status=MaintenanceRequestStatus.PROCESSING.value,
                claim_token=claim_token,
                lease_expires_at=lease_expires_at,
                report_id=None,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(
                index_elements=[MaintenanceReportRequestModel.idempotency_key_digest]
            )
            .returning(MaintenanceReportRequestModel.idempotency_key_digest)
        )
        if inserted is not None:
            return MaintenanceRequestClaim(
                disposition=ClaimDisposition.CLAIMED,
                claim_token=claim_token,
            )

        model = await self._session.scalar(
            select(MaintenanceReportRequestModel)
            .where(
                MaintenanceReportRequestModel.idempotency_key_digest
                == identity.idempotency_key_digest
            )
            .with_for_update()
        )
        if model is None:
            raise IdempotencyPersistenceIntegrityError(
                "Idempotency reservation disappeared during claim"
            )
        if model.request_digest != identity.request_digest:
            return MaintenanceRequestClaim(disposition=ClaimDisposition.CONFLICT)
        if model.machine_id != identity.machine_id or model.modality != identity.modality.value:
            raise IdempotencyPersistenceIntegrityError(
                "Idempotency request metadata does not match its fingerprint"
            )
        if model.status == MaintenanceRequestStatus.COMPLETED.value:
            if model.report_id is None:
                raise IdempotencyPersistenceIntegrityError(
                    "Completed idempotency reservation has no report"
                )
            return MaintenanceRequestClaim(
                disposition=ClaimDisposition.COMPLETED,
                report_id=model.report_id,
            )
        if model.status != MaintenanceRequestStatus.PROCESSING.value:
            raise IdempotencyPersistenceIntegrityError(
                "Idempotency reservation has an unknown state"
            )
        if model.lease_expires_at is None or model.claim_token is None:
            raise IdempotencyPersistenceIntegrityError(
                "Processing idempotency reservation has no active claim"
            )
        if model.lease_expires_at > now:
            return MaintenanceRequestClaim(disposition=ClaimDisposition.IN_PROGRESS)

        model.claim_token = claim_token
        model.lease_expires_at = lease_expires_at
        model.updated_at = now
        await self._session.flush()
        return MaintenanceRequestClaim(
            disposition=ClaimDisposition.CLAIMED,
            claim_token=claim_token,
        )

    async def release(
        self,
        identity: MaintenanceRequestIdentity,
        claim_token: UUID,
    ) -> bool:
        released = await self._session.scalar(
            delete(MaintenanceReportRequestModel)
            .where(
                MaintenanceReportRequestModel.idempotency_key_digest
                == identity.idempotency_key_digest,
                MaintenanceReportRequestModel.request_digest == identity.request_digest,
                MaintenanceReportRequestModel.status == MaintenanceRequestStatus.PROCESSING.value,
                MaintenanceReportRequestModel.claim_token == claim_token,
            )
            .returning(MaintenanceReportRequestModel.idempotency_key_digest)
        )
        return released is not None

    async def complete(
        self,
        identity: MaintenanceRequestIdentity,
        claim_token: UUID,
        report_id: UUID,
        *,
        completed_at: datetime,
    ) -> bool:
        completed = await self._session.scalar(
            update(MaintenanceReportRequestModel)
            .where(
                MaintenanceReportRequestModel.idempotency_key_digest
                == identity.idempotency_key_digest,
                MaintenanceReportRequestModel.request_digest == identity.request_digest,
                MaintenanceReportRequestModel.status == MaintenanceRequestStatus.PROCESSING.value,
                MaintenanceReportRequestModel.claim_token == claim_token,
            )
            .values(
                status=MaintenanceRequestStatus.COMPLETED.value,
                claim_token=None,
                lease_expires_at=None,
                report_id=report_id,
                updated_at=completed_at,
            )
            .returning(MaintenanceReportRequestModel.idempotency_key_digest)
        )
        return completed is not None
