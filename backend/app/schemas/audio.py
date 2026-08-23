from uuid import UUID

from pydantic import BaseModel, Field

from domain.enums.modality import Modality


class AudioPredictionResponse(BaseModel):
    machine_id: UUID
    modality: Modality
    label: str
    confidence: float = Field(ge=0, le=1)
