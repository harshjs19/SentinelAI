from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from backend.app.readiness import database_is_ready

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


DatabaseReadiness = Annotated[bool, Depends(database_is_ready)]


@router.get("/ready", response_model=None)
async def readiness_check(database_ready: DatabaseReadiness) -> dict[str, str] | JSONResponse:
    if not database_ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready"},
        )
    return {"status": "ready"}
