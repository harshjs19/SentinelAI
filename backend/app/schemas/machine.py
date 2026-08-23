from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MachineCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1)
    asset_type: str = Field(min_length=1)


class MachineResponse(BaseModel):
    id: UUID
    name: str
    asset_type: str
