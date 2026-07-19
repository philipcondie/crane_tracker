import uuid
from datetime import datetime

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import CheckConstraint, Float, Index, String, Text, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from uuid_utils import uuid7


class Base(DeclarativeBase):
    pass


def generate_uuid7() -> uuid.UUID:
    return uuid.UUID(str(uuid7()))


class Crane(Base):
    __tablename__ = "crane"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=generate_uuid7
    )
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    location: Mapped[WKBElement] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False)
    )
    project_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(Text, default="active")
    city: Mapped[str] = mapped_column(Text, nullable=True)
    neighborhood: Mapped[str] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("lat >= -90 AND lat <= 90", name="ck_crane_lat_range"),
        CheckConstraint("lng >= -180 AND lng <= 180", name="ck_crane_lng_range"),
        Index("idx_cranes_location", "location", postgresql_using="gist"),
    )
