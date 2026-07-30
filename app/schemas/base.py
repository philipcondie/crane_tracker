import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CraneStatus(StrEnum):
    ACTIVE = "active"
    GONE = "gone"


class BaseApiSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True, populate_by_name=True, alias_generator=to_camel
    )


class CraneInput(BaseApiSchema):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    project_name: str | None = None


class CreateCraneRequest(CraneInput):
    override_duplicate_warning: bool = False


class CranePhotoResponse(BaseApiSchema):
    id: uuid.UUID
    crane_id: uuid.UUID
    url: str
    original_filename: str
    content_type: str
    added_at: datetime


class CraneSummary(BaseApiSchema):
    id: uuid.UUID
    lat: float
    lng: float
    project_name: str | None
    status: CraneStatus
    city: str | None
    neighborhood: str | None
    photos: int = 0
    contribs: int = 0  # placeholder value until contribs is added in v1
    added_at: datetime


class CraneDetail(CraneSummary):
    photo_items: list[CranePhotoResponse] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)  # placeholder until links are added


class CraneListResponse(BaseApiSchema):
    cranes: list[CraneSummary]
    truncated: bool
