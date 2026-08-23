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
from backend.app.services.timeseries_inference_service import TimeseriesInferenceService
from domain.enums.modality import Modality
from inference.event_bus import EventBus
from inference.orchestrator import InferenceOrchestrator
from modules.audio.input import AudioInput
from modules.audio.predictor import AudioPredictor
from modules.decision.engine import DecisionEngine
from modules.timeseries.predictor import TimeseriesPredictor

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
    artifact_path = get_settings().audio_model_path
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Audio model artifact not found: {artifact_path}")
    return AudioPredictor(artifact_path)


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
