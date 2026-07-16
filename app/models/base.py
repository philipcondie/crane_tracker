import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Float, String, Text, Uuid, func
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
    project_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(Text, default="active")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("lat >= -90 AND lat <= 90", name="ck_crane_lat_range"),
        CheckConstraint("lng >= -180 AND lng <= 180", name="ck_crane_lng_range"),
    )
