from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies import (
    get_decision_service,
    get_machine_service,
    get_timeseries_inference_service,
)
from backend.app.schemas.analysis import AnalysisResponse, FindingResponse
from backend.app.schemas.timeseries import TimeseriesPredictionRequest
from backend.app.services.decision_service import DecisionService
from backend.app.services.machine_service import MachineService
from backend.app.services.timeseries_inference_service import TimeseriesInferenceService

router = APIRouter(prefix="/machines", tags=["analyses"])
MachineServiceDependency = Annotated[MachineService, Depends(get_machine_service)]
TimeseriesInferenceDependency = Annotated[
    TimeseriesInferenceService,
    Depends(get_timeseries_inference_service),
]
DecisionServiceDependency = Annotated[DecisionService, Depends(get_decision_service)]


@router.post(
    "/{machine_id}/analyses/timeseries",
    response_model=AnalysisResponse,
)
async def analyze_timeseries(
    machine_id: UUID,
    request: TimeseriesPredictionRequest,
    machine_service: MachineServiceDependency,
    inference_service: TimeseriesInferenceDependency,
    decision_service: DecisionServiceDependency,
) -> AnalysisResponse:
    machine = await machine_service.get_machine(machine_id)
    if machine is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")

    prediction = await inference_service.predict(
        machine_id,
        [sample.model_dump() for sample in request.samples],
    )
    analysis = await decision_service.analyze(machine_id, [prediction])
    return AnalysisResponse(
        machine_id=machine_id,
        status=analysis.status,
        condition=analysis.condition,
        findings=[FindingResponse.model_validate(finding) for finding in analysis.findings],
        top_findings=[FindingResponse.model_validate(finding) for finding in analysis.top_findings],
        health_score=(analysis.health_score.value if analysis.health_score is not None else None),
        risk_level=analysis.risk_level,
        limitations=list(analysis.limitations),
    )
