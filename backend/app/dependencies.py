from collections.abc import Mapping
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import get_settings
from backend.app.db.session import get_session
from backend.app.repositories.sqlalchemy_machine_repository import (
    SQLAlchemyMachineRepository,
)
from backend.app.services.audio_inference_service import AudioInferenceService
from backend.app.services.decision_service import DecisionService
from backend.app.services.machine_service import MachineService
from backend.app.services.thermal_inference_service import ThermalInferenceService
from backend.app.services.timeseries_inference_service import TimeseriesInferenceService
from backend.app.services.vision_inference_service import VisionInferenceService
from domain.enums.modality import Modality
from inference.event_bus import EventBus
from inference.orchestrator import InferenceOrchestrator
from modules.audio.input import AudioInput
from modules.audio.predictor import AudioPredictor
from modules.decision.engine import DecisionEngine
from modules.thermal.input import ThermalInput
from modules.thermal.predictor import ThermalPredictor
from modules.timeseries.predictor import TimeseriesPredictor
from modules.vision.input import VisionInput
from modules.vision.predictor import VisionPredictor

SessionDependency = Annotated[AsyncSession, Depends(get_session, scope="function")]


def get_machine_service(session: SessionDependency) -> MachineService:
    return MachineService(SQLAlchemyMachineRepository(session))


@lru_cache
def get_event_bus() -> EventBus:
    return EventBus()


@lru_cache
def get_decision_engine() -> DecisionEngine:
    return DecisionEngine()


@lru_cache
def get_decision_service() -> DecisionService:
    return DecisionService(get_decision_engine(), get_event_bus())


@lru_cache
def get_timeseries_predictor() -> TimeseriesPredictor:
    artifact_path = get_settings().timeseries_model_path
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Time-series model artifact not found: {artifact_path}")
    return TimeseriesPredictor(artifact_path)


@lru_cache
def get_inference_orchestrator() -> InferenceOrchestrator:
    return InferenceOrchestrator(get_event_bus())


@lru_cache
def get_timeseries_inference_service() -> TimeseriesInferenceService:
    try:
        orchestrator = get_inference_orchestrator()
        orchestrator.register(
            Modality.TIMESERIES,
            get_timeseries_predictor(),
            input_type=Mapping,
        )
        return TimeseriesInferenceService(orchestrator)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Time-series model is not available",
        ) from None


@lru_cache
def get_audio_predictor() -> AudioPredictor:
    settings = get_settings()
    artifact_path = settings.audio_model_path
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Audio model artifact not found: {artifact_path}")
    return AudioPredictor(
        artifact_path,
        encoder_path=settings.audio_encoder_path,
        device=settings.audio_encoder_device,
    )


@lru_cache
def get_audio_inference_service() -> AudioInferenceService:
    try:
        predictor = get_audio_predictor()
        orchestrator = get_inference_orchestrator()
        orchestrator.register(Modality.AUDIO, predictor, input_type=AudioInput)
        return AudioInferenceService(orchestrator, predictor.supported_asset_types)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Audio model is not available",
        ) from None


@lru_cache
def get_vision_predictor() -> VisionPredictor:
    settings = get_settings()
    artifact_path = settings.vision_model_path
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Vision model artifact not found: {artifact_path}")
    return VisionPredictor(
        artifact_path,
        encoder_path=settings.vision_encoder_path,
        device=settings.vision_device,
    )


@lru_cache
def get_vision_inference_service() -> VisionInferenceService:
    try:
        predictor = get_vision_predictor()
        orchestrator = get_inference_orchestrator()
        orchestrator.register(Modality.VISION, predictor, input_type=VisionInput)
        return VisionInferenceService(orchestrator, predictor.supported_asset_types)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vision model is not available",
        ) from None


@lru_cache
def get_thermal_predictor() -> ThermalPredictor:
    settings = get_settings()
    artifact_path = settings.thermal_model_path
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Thermal model artifact not found: {artifact_path}")
    return ThermalPredictor(
        artifact_path,
        encoder_path=settings.thermal_encoder_path,
        device=settings.thermal_device,
    )


@lru_cache
def get_thermal_inference_service() -> ThermalInferenceService:
    try:
        predictor = get_thermal_predictor()
        orchestrator = get_inference_orchestrator()
        orchestrator.register(Modality.THERMAL, predictor, input_type=ThermalInput)
        return ThermalInferenceService(orchestrator, predictor.supported_asset_types)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Thermal model is not available",
        ) from None
