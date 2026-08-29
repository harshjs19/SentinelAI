from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.analyses import router as analyses_router
from backend.app.api.capabilities import router as capabilities_router
from backend.app.api.health import router as health_router
from backend.app.api.machines import router as machines_router
from backend.app.api.maintenance_reports import router as maintenance_reports_router
from backend.app.api.predictions import router as predictions_router
from backend.app.config import get_settings
from backend.app.observability import (
    RequestObservabilityMiddleware,
    configure_application_logging,
    log_startup,
)

APP_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_application_logging(settings)
    log_startup(settings, APP_VERSION)
    yield


app = FastAPI(
    title="SentinelAI",
    version=APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(RequestObservabilityMiddleware)

app.include_router(health_router)
app.include_router(capabilities_router)
app.include_router(machines_router)
app.include_router(predictions_router)
app.include_router(analyses_router)
app.include_router(maintenance_reports_router)
