from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from domain.enums.modality import Modality


class TimeseriesSample(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    ch1_bias: float
    ch1_derivedPk: float
    ch1_direct: float
    ch1_directRMS: float
    ch1_velocityPk: float
    ch1_velocityRMS: float


class TimeseriesPredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    samples: list[TimeseriesSample] = Field(min_length=2)


class TimeseriesPredictionResponse(BaseModel):
    machine_id: UUID
    modality: Modality
    label: str
    confidence: float = Field(ge=0, le=1)
