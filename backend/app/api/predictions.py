from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from backend.app.dependencies import (
    get_audio_inference_service,
    get_machine_service,
    get_thermal_inference_service,
    get_timeseries_inference_service,
    get_vision_inference_service,
)
from backend.app.schemas.audio import AudioPredictionResponse
from backend.app.schemas.thermal import ThermalPredictionResponse
from backend.app.schemas.timeseries import (
    TimeseriesPredictionRequest,
    TimeseriesPredictionResponse,
)
from backend.app.schemas.vision import VisionPredictionResponse
from backend.app.services.audio_inference_service import (
    AudioInferenceService,
    UnsupportedAudioAssetTypeError,
)
from backend.app.services.machine_service import MachineService
from backend.app.services.thermal_inference_service import (
    ThermalInferenceService,
    UnsupportedThermalAssetTypeError,
)
from backend.app.services.timeseries_inference_service import TimeseriesInferenceService
from backend.app.services.vision_inference_service import (
    UnsupportedVisionAssetTypeError,
    VisionInferenceService,
)

router = APIRouter(prefix="/machines", tags=["predictions"])
MachineServiceDependency = Annotated[MachineService, Depends(get_machine_service)]
TimeseriesInferenceDependency = Annotated[
    TimeseriesInferenceService,
    Depends(get_timeseries_inference_service),
]
AudioInferenceDependency = Annotated[AudioInferenceService, Depends(get_audio_inference_service)]
VisionInferenceDependency = Annotated[VisionInferenceService, Depends(get_vision_inference_service)]
ThermalInferenceDependency = Annotated[
    ThermalInferenceService,
    Depends(get_thermal_inference_service),
]


@router.post(
    "/{machine_id}/predictions/timeseries",
    response_model=TimeseriesPredictionResponse,
)
async def predict_timeseries(
    machine_id: UUID,
    request: TimeseriesPredictionRequest,
    machine_service: MachineServiceDependency,
    inference_service: TimeseriesInferenceDependency,
) -> TimeseriesPredictionResponse:
    machine = await machine_service.get_machine(machine_id)
    if machine is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")

    result = await inference_service.predict(
        machine_id,
        [sample.model_dump() for sample in request.samples],
    )
    prediction = result.prediction
    return TimeseriesPredictionResponse(
        machine_id=machine_id,
        modality=prediction.modality,
        label=prediction.label,
        confidence=prediction.confidence,
    )


@router.post(
    "/{machine_id}/predictions/audio",
    response_model=AudioPredictionResponse,
)
async def predict_audio(
    machine_id: UUID,
    file: Annotated[UploadFile, File(description="WAV audio clip")],
    machine_service: MachineServiceDependency,
    inference_service: AudioInferenceDependency,
) -> AudioPredictionResponse:
    machine = await machine_service.get_machine(machine_id)
    if machine is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")

    try:
        inference_service.validate_asset_type(machine.asset_type)
    except UnsupportedAudioAssetTypeError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from None

    try:
        result = await inference_service.predict(machine_id, await file.read())
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    prediction = result.prediction
    return AudioPredictionResponse(
        machine_id=machine_id,
        modality=prediction.modality,
        label=prediction.label,
        confidence=prediction.confidence,
    )


@router.post(
    "/{machine_id}/predictions/vision",
    response_model=VisionPredictionResponse,
)
async def predict_vision(
    machine_id: UUID,
    file: Annotated[UploadFile, File(description="JPEG or PNG industrial image")],
    machine_service: MachineServiceDependency,
    inference_service: VisionInferenceDependency,
) -> VisionPredictionResponse:
    machine = await machine_service.get_machine(machine_id)
    if machine is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")
    try:
        inference_service.validate_asset_type(machine.asset_type)
    except UnsupportedVisionAssetTypeError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from None
    try:
        result = await inference_service.predict(machine_id, await file.read())
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    prediction = result.prediction
    return VisionPredictionResponse(
        machine_id=machine_id,
        modality=prediction.modality,
        label=prediction.label,
        confidence=prediction.confidence,
    )


@router.post(
    "/{machine_id}/predictions/thermal",
    response_model=ThermalPredictionResponse,
)
async def predict_thermal(
    machine_id: UUID,
    file: Annotated[UploadFile, File(description="JPEG or PNG thermographic image")],
    machine_service: MachineServiceDependency,
    inference_service: ThermalInferenceDependency,
) -> ThermalPredictionResponse:
    machine = await machine_service.get_machine(machine_id)
    if machine is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")
    try:
        inference_service.validate_asset_type(machine.asset_type)
    except UnsupportedThermalAssetTypeError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from None
    try:
        result = await inference_service.predict(machine_id, await file.read())
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    prediction = result.prediction
    return ThermalPredictionResponse(
        machine_id=machine_id,
        modality=prediction.modality,
        label=prediction.label,
        confidence=prediction.confidence,
    )
