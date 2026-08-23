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
from backend.app.services.machine_service import MachineService
from backend.app.services.timeseries_inference_service import TimeseriesInferenceService
from domain.enums.modality import Modality
from inference.event_bus import EventBus
from inference.orchestrator import InferenceOrchestrator
from modules.timeseries.predictor import TimeseriesPredictor

SessionDependency = Annotated[AsyncSession, Depends(get_session, scope="function")]


def get_machine_service(session: SessionDependency) -> MachineService:
    return MachineService(SQLAlchemyMachineRepository(session))


@lru_cache
def get_event_bus() -> EventBus:
    return EventBus()


@lru_cache
def get_timeseries_predictor() -> TimeseriesPredictor:
    artifact_path = get_settings().timeseries_model_path
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Time-series model artifact not found: {artifact_path}")
    return TimeseriesPredictor(artifact_path)


@lru_cache
def get_inference_orchestrator() -> InferenceOrchestrator:
    orchestrator = InferenceOrchestrator(get_event_bus())
    orchestrator.register(
        Modality.TIMESERIES,
        get_timeseries_predictor(),
        input_type=Mapping,
    )
    return orchestrator


@lru_cache
def get_timeseries_inference_service() -> TimeseriesInferenceService:
    try:
        return TimeseriesInferenceService(get_inference_orchestrator())
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Time-series model is not available",
        ) from None
