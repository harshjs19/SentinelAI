from pydantic import BaseModel

from ai_core.model_capabilities import ModelLifecycleStatus
from domain.enums.modality import Modality


class ModelCapabilityResponse(BaseModel):
    model_id: str
    modality: Modality
    status: ModelLifecycleStatus
    runtime_default: bool
    validated_scope: str
    evaluation_reference: str


class ModelCapabilitiesResponse(BaseModel):
    models: list[ModelCapabilityResponse]
