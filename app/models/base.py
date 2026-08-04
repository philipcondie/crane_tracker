import enum
import uuid
from datetime import datetime

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    CheckConstraint,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
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
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
    photo_records: Mapped[list["CranePhoto"]] = relationship(
        back_populates="crane",
        cascade="all, delete-orphan",
        order_by=lambda: (CranePhoto.added_at, CranePhoto.id),
    )

    __table_args__ = (
        CheckConstraint("lat >= -90 AND lat <= 90", name="ck_crane_lat_range"),
        CheckConstraint("lng >= -180 AND lng <= 180", name="ck_crane_lng_range"),
        Index("idx_cranes_location", "location", postgresql_using="gist"),
    )


class CranePhotoStatus(enum.StrEnum):
    ACTIVE = "active"
    PENDING_UPLOAD = "pending_upload"
    PENDING_DELETE = "pending_delete"


crane_photo_status_type = Enum(
    CranePhotoStatus,
    name="crane_photo_status",
    values_callable=lambda enum_class: [member.value for member in enum_class],
)


class CranePhoto(Base):
    __tablename__ = "crane_photo"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=generate_uuid7
    )
    crane_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("crane.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())
    status: Mapped[CranePhotoStatus] = mapped_column(
        crane_photo_status_type, nullable=False, default=CranePhotoStatus.PENDING_UPLOAD
    )

    crane: Mapped[Crane] = relationship(back_populates="photo_records")


class GoneReport(Base):
    __tablename__ = "gone_report"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=generate_uuid7
    )
    crane_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("crane.id", ondelete="CASCADE")
    )
    reporter_ip_hash: Mapped[str] = mapped_column(String)
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        UniqueConstraint("crane_id", "reporter_ip_hash", name="crane_reporter"),
    )


class JobOperation(enum.StrEnum):
    DELETE = "delete"


job_operation_type = Enum(
    JobOperation,
    name="job_operation",
    values_callable=lambda enum_class: [member.value for member in enum_class],
)


class JobStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


job_status_type = Enum(
    JobStatus,
    name="job_status",
    values_callable=lambda enum_class: [member.value for member in enum_class],
)


class OutboxJob(Base):
    __tablename__ = "outbox_job"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=generate_uuid7
    )
    operation: Mapped[JobOperation] = mapped_column(job_operation_type, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024))
    status: Mapped[JobStatus] = mapped_column(
        job_status_type, nullable=False, default=JobStatus.PENDING
    )
    attempts: Mapped[int] = mapped_column(
        Integer, default=0
    )  # starts at 0 and increments up
    available_at: Mapped[datetime] = mapped_column(
        server_default=func.now()
    )  # controls the backoff on errors
    lease_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
