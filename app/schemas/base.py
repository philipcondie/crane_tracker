import uuid
from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CraneStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class BaseApiSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True, populate_by_name=True, alias_generator=to_camel
    )


class CraneCreate(BaseApiSchema):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    project_name: str | None = None
    status: CraneStatus


class CraneSummary(BaseApiSchema):
    id: uuid.UUID
    lat: float
    lng: float
    project_name: str | None
    status: CraneStatus
    city: str | None
    neighborhood: str | None
    photos: int = 0  # placeholder value until photos is added in v1
    contribs: int = 0  # placeholder value until contribs is added in v1
    added_at: datetime


class CraneDetail(CraneSummary):
    imgs: list[str] = []  # placeholder until later tables are added
    links: list[str] = []  # placeholder until later tables are added


class CraneListResponse(BaseApiSchema):
    cranes: list[CraneSummary]
    truncated: bool