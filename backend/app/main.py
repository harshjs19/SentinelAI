from fastapi import FastAPI

from backend.app.api.health import router as health_router
from backend.app.api.machines import router as machines_router
from backend.app.api.predictions import router as predictions_router

app = FastAPI(
    title="SentinelAI",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(machines_router)
app.include_router(predictions_router)
