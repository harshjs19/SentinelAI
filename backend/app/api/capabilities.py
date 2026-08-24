from fastapi import APIRouter

from ai_core.model_capabilities import MODEL_CAPABILITIES
from backend.app.schemas.capability import ModelCapabilitiesResponse, ModelCapabilityResponse

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


@router.get("/models", response_model=ModelCapabilitiesResponse)
async def list_model_capabilities() -> ModelCapabilitiesResponse:
    return ModelCapabilitiesResponse(
        models=[
            ModelCapabilityResponse.model_validate(capability, from_attributes=True)
            for capability in MODEL_CAPABILITIES
        ]
    )
