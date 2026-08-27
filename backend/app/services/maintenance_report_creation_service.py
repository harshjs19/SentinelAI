from dataclasses import dataclass

from backend.app.persistence.errors import ArtifactPersistenceIntegrityError
from backend.app.services.maintenance_request_idempotency_service import (
    MaintenanceRequestIdempotencyService,
    ReservationDisposition,
)
from backend.app.services.maintenance_workflow_persistence_service import (
    MaintenanceWorkflowPersistenceService,
)
from backend.app.services.maintenance_workflow_service import (
    MaintenanceWorkflowRequest,
    MaintenanceWorkflowService,
)
from modules.copilot.report import MaintenanceReport


@dataclass(frozen=True)
class MaintenanceReportCreationResult:
    report: MaintenanceReport
    replayed: bool


class MaintenanceReportCreationService:
    def __init__(
        self,
        *,
        workflow_service: MaintenanceWorkflowService,
        persistence_service: MaintenanceWorkflowPersistenceService,
        idempotency_service: MaintenanceRequestIdempotencyService,
    ) -> None:
        self._workflow_service = workflow_service
        self._persistence_service = persistence_service
        self._idempotency_service = idempotency_service

    async def create(
        self,
        request: MaintenanceWorkflowRequest,
        idempotency_key: str,
    ) -> MaintenanceReportCreationResult:
        reservation = await self._idempotency_service.reserve(idempotency_key, request)
        if reservation.disposition is ReservationDisposition.REPLAY:
            if reservation.report_id is None:
                raise ArtifactPersistenceIntegrityError(
                    "Completed maintenance request has no report reference"
                )
            historical = await self._persistence_service.get_by_report_id(reservation.report_id)
            if historical is None:
                raise ArtifactPersistenceIntegrityError(
                    "Completed maintenance request report is unavailable"
                )
            return MaintenanceReportCreationResult(
                report=historical.maintenance_report,
                replayed=True,
            )

        try:
            result = await self._workflow_service.execute(request)
        except Exception as workflow_error:
            try:
                await self._idempotency_service.release(reservation)
            except Exception as release_error:
                raise workflow_error from release_error
            raise

        reference = await self._persistence_service.persist(result)
        await self._idempotency_service.complete(
            reservation,
            reference.maintenance_report_id,
        )
        return MaintenanceReportCreationResult(
            report=result.maintenance_report,
            replayed=False,
        )
