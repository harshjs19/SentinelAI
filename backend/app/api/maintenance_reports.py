from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)

from backend.app.dependencies import (
    get_machine_service,
    get_maintenance_report_creation_service,
    get_maintenance_workflow_persistence_service,
)
from backend.app.persistence.errors import ArtifactPersistenceIntegrityError
from backend.app.repositories.sqlalchemy_maintenance_request_idempotency_repository import (
    IdempotencyPersistenceIntegrityError,
)
from backend.app.schemas.maintenance_report import (
    MaintenanceReportResponse,
    MaintenanceReportSummaryResponse,
    TimeseriesMaintenanceReportRequest,
)
from backend.app.services.audio_inference_service import UnsupportedAudioAssetTypeError
from backend.app.services.machine_service import MachineService
from backend.app.services.maintenance_report_creation_service import (
    MaintenanceReportCreationResult,
    MaintenanceReportCreationService,
)
from backend.app.services.maintenance_request_idempotency_service import (
    MAX_IDEMPOTENCY_KEY_CHARACTERS,
    IdempotencyClaimLostError,
    IdempotencyConflictError,
    IdempotencyInProgressError,
    InvalidIdempotencyKeyError,
)
from backend.app.services.maintenance_workflow_persistence_service import (
    MaintenanceWorkflowPersistenceService,
)
from backend.app.services.maintenance_workflow_service import (
    AudioMaintenanceRequest,
    MaintenanceWorkflowIntegrityError,
    MaintenanceWorkflowMachineNotFoundError,
    MaintenanceWorkflowRequest,
    ThermalMaintenanceRequest,
    TimeseriesMaintenanceRequest,
    VisionMaintenanceRequest,
)
from backend.app.services.thermal_inference_service import UnsupportedThermalAssetTypeError
from backend.app.services.vision_inference_service import UnsupportedVisionAssetTypeError
from modules.copilot.contracts import MAX_QUESTION_CHARACTERS, CopilotIntent
from modules.retriever.exceptions import RetrievalUnavailableError

router = APIRouter(tags=["maintenance reports"])

CreationServiceDependency = Annotated[
    MaintenanceReportCreationService,
    Depends(get_maintenance_report_creation_service),
]
PersistenceServiceDependency = Annotated[
    MaintenanceWorkflowPersistenceService,
    Depends(get_maintenance_workflow_persistence_service),
]
MachineServiceDependency = Annotated[MachineService, Depends(get_machine_service)]
IdempotencyKeyHeader = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=MAX_IDEMPOTENCY_KEY_CHARACTERS,
    ),
]
MaintenanceFile = Annotated[UploadFile, File()]
MaintenanceIntent = Annotated[CopilotIntent, Form()]
MaintenanceQuestion = Annotated[
    str | None,
    Form(max_length=MAX_QUESTION_CHARACTERS),
]


@router.post(
    "/machines/{machine_id}/maintenance-reports/timeseries",
    response_model=MaintenanceReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_timeseries_maintenance_report(
    machine_id: UUID,
    request: TimeseriesMaintenanceReportRequest,
    response: Response,
    service: CreationServiceDependency,
    idempotency_key: IdempotencyKeyHeader,
) -> MaintenanceReportResponse:
    samples = tuple(sample.model_dump() for sample in request.samples)
    return await _create_report(
        TimeseriesMaintenanceRequest(
            machine_id=machine_id,
            samples=samples,
            intent=request.intent,
            question=request.question,
        ),
        idempotency_key,
        response,
        service,
    )


@router.post(
    "/machines/{machine_id}/maintenance-reports/audio",
    response_model=MaintenanceReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_audio_maintenance_report(
    machine_id: UUID,
    file: MaintenanceFile,
    intent: MaintenanceIntent,
    response: Response,
    service: CreationServiceDependency,
    idempotency_key: IdempotencyKeyHeader,
    question: MaintenanceQuestion = None,
) -> MaintenanceReportResponse:
    content = await file.read()
    return await _create_report(
        AudioMaintenanceRequest(
            machine_id=machine_id,
            content=content,
            intent=intent,
            question=question,
        ),
        idempotency_key,
        response,
        service,
    )


@router.post(
    "/machines/{machine_id}/maintenance-reports/vision",
    response_model=MaintenanceReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_vision_maintenance_report(
    machine_id: UUID,
    file: MaintenanceFile,
    intent: MaintenanceIntent,
    response: Response,
    service: CreationServiceDependency,
    idempotency_key: IdempotencyKeyHeader,
    question: MaintenanceQuestion = None,
) -> MaintenanceReportResponse:
    content = await file.read()
    return await _create_report(
        VisionMaintenanceRequest(
            machine_id=machine_id,
            content=content,
            intent=intent,
            question=question,
        ),
        idempotency_key,
        response,
        service,
    )


@router.post(
    "/machines/{machine_id}/maintenance-reports/thermal",
    response_model=MaintenanceReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_thermal_maintenance_report(
    machine_id: UUID,
    file: MaintenanceFile,
    intent: MaintenanceIntent,
    response: Response,
    service: CreationServiceDependency,
    idempotency_key: IdempotencyKeyHeader,
    question: MaintenanceQuestion = None,
) -> MaintenanceReportResponse:
    content = await file.read()
    return await _create_report(
        ThermalMaintenanceRequest(
            machine_id=machine_id,
            content=content,
            intent=intent,
            question=question,
        ),
        idempotency_key,
        response,
        service,
    )


@router.get(
    "/maintenance-reports/{report_id}",
    response_model=MaintenanceReportResponse,
)
async def get_maintenance_report(
    report_id: UUID,
    service: PersistenceServiceDependency,
) -> MaintenanceReportResponse:
    try:
        historical = await service.get_by_report_id(report_id)
    except ArtifactPersistenceIntegrityError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored maintenance report failed integrity verification",
        ) from None
    if historical is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance report not found",
        )
    return MaintenanceReportResponse.from_domain(historical.maintenance_report)


@router.get(
    "/machines/{machine_id}/maintenance-reports",
    response_model=list[MaintenanceReportSummaryResponse],
)
async def list_machine_maintenance_reports(
    machine_id: UUID,
    service: PersistenceServiceDependency,
    machine_service: MachineServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[MaintenanceReportSummaryResponse]:
    machine = await machine_service.get_machine(machine_id)
    if machine is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Machine not found",
        )
    try:
        historical = await service.list_for_machine(
            machine_id,
            limit=limit,
            offset=offset,
        )
    except ArtifactPersistenceIntegrityError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored maintenance report history failed integrity verification",
        ) from None
    return [
        MaintenanceReportSummaryResponse.from_domain(item.maintenance_report) for item in historical
    ]


async def _create_report(
    request: MaintenanceWorkflowRequest,
    idempotency_key: str,
    response: Response,
    service: MaintenanceReportCreationService,
) -> MaintenanceReportResponse:
    try:
        result = await service.create(request, idempotency_key)
    except InvalidIdempotencyKeyError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from None
    except IdempotencyConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key conflicts with a different request",
        ) from None
    except IdempotencyInProgressError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An identical maintenance request is already processing",
        ) from None
    except IdempotencyClaimLostError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Maintenance request processing claim is no longer active",
        ) from None
    except MaintenanceWorkflowMachineNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Machine not found",
        ) from None
    except (
        UnsupportedAudioAssetTypeError,
        UnsupportedVisionAssetTypeError,
        UnsupportedThermalAssetTypeError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from None
    except RetrievalUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Maintenance knowledge retrieval is not available",
        ) from None
    except (
        ArtifactPersistenceIntegrityError,
        IdempotencyPersistenceIntegrityError,
        MaintenanceWorkflowIntegrityError,
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Maintenance report could not be completed safely",
        ) from None
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from None

    _set_replay_response(response, result)
    return MaintenanceReportResponse.from_domain(result.report)


def _set_replay_response(
    response: Response,
    result: MaintenanceReportCreationResult,
) -> None:
    if result.replayed:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replay"] = "true"
