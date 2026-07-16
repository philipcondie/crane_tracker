import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class CraneStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class CraneCreate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    project_name: str | None = None
    status: CraneStatus


class CraneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    lat: float
    lng: float
    project_name: str | None
    status: CraneStatus
