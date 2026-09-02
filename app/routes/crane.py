import logging
import uuid

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import app.services.crane as crane_service
import app.services.photo as photo_service
import app.services.storage as storage_service
from app.core.config import get_settings
from app.core.dependencies import SessionDep
from app.core.exceptions import (
    InvalidCoordinateError,
    PhotoStorageError,
    PhotoUploadRaceError,
)
from app.core.limiter import limiter
from app.models.base import CranePhoto
from app.schemas.base import (
    CraneDetail,
    CraneInput,
    CraneListResponse,
    CranePhotoResponse,
    CraneSummary,
    CreateCraneRequest,
    PhotoListResponse,
)

logger = logging.getLogger(__name__)

settings = get_settings()

crane_router = APIRouter(prefix="/cranes")


def serialize_crane_photo(photo: CranePhoto) -> CranePhotoResponse:
    return CranePhotoResponse(
        id=photo.id,
        crane_id=photo.crane_id,
        url=storage_service.get_public_url(object_key=photo.storage_key),
        original_filename=photo.original_filename,
        content_type=photo.content_type,
        added_at=photo.added_at,
    )


@crane_router.post("", response_model=CraneSummary, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.create_rate_limit)
def create_crane(
    request: Request, session: SessionDep, create_request: CreateCraneRequest
):
    crane_input = CraneInput(
        lat=create_request.lat,
        lng=create_request.lng,
        project_name=create_request.project_name,
    )

    crane = crane_service.create_crane(
        session=session,
        input=crane_input,
        override_duplicate_warning=create_request.override_duplicate_warning,
    )
    session.commit()
    logger.info("crane_created", extra={"crane_id": str(crane.id)})
    return crane


@crane_router.get("/{crane_id}", response_model=CraneDetail)
def get_crane(session: SessionDep, crane_id: uuid.UUID):
    crane = crane_service.get_crane(session=session, id=crane_id)
    photo_items = [serialize_crane_photo(photo) for photo in crane.photo_records]

    detail = CraneDetail.model_validate(crane)
    detail.photos = len(crane.photo_records)
    detail.photo_items = photo_items
    return detail


@crane_router.get("", response_model=CraneListResponse)
def get_cranes(
    session: SessionDep,
    north: float = Query(ge=-90, le=90),
    south: float = Query(ge=-90, le=90),
    east: float = Query(ge=-180, le=180),
    west: float = Query(ge=-180, le=180),
):
    try:
        cranes = crane_service.get_cranes(
            session=session, north=north, south=south, east=east, west=west
        )
    except InvalidCoordinateError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)
        )
    return cranes


@crane_router.post("/{crane_id}/report")
def report_crane_as_gone(session: SessionDep, crane_id: uuid.UUID, request: Request):
    client_ip = request.client.host if request.client else None

    if client_ip is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="could not identify host to record report",
        )

    crane_service.report_crane_as_gone(
        session=session, crane_id=crane_id, client_ip=client_ip
    )
    session.commit()


def _abandon_helper(session: Session, photo_id: uuid.UUID, crane_id: uuid.UUID):
    try:
        photo_service.abandon_crane_photo_upload(session=session, photo_id=photo_id)
        session.commit()
        logger.info(
            "crane_photo_delete_job_added",
            extra={"crane_id": str(crane_id), "photo_id": str(photo_id)},
        )
    except Exception:
        session.rollback()
        logger.exception(
            "crane_photo_upload_abandon_failed",
            extra={"crane_id": str(crane_id), "photo_id": str(photo_id)},
        )


@crane_router.post(
    "/{crane_id}/photos",
    response_model=CranePhotoResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(settings.create_rate_limit)
def upload_crane_photo(
    request: Request,
    session: SessionDep,
    crane_id: uuid.UUID,
    photo: UploadFile = File(...),
):
    crane_photo = None
    photo_id = None
    try:
        crane_photo, prepared_file = photo_service.preupload_crane_photo(
            session=session,
            crane_id=crane_id,
            file=photo.file,
            filename=photo.filename or "photo",
            content_type=photo.content_type or "application/octet-stream",
        )
        photo_id = crane_photo.id
        storage_key = crane_photo.storage_key
        content_type = crane_photo.content_type
        session.commit()  # required to close out transaction before next steps

        try:
            photo_service.upload_crane_photo_to_storage(
                photo_id=photo_id,
                crane_id=crane_id,
                storage_key=storage_key,
                content_type=content_type,
                file=prepared_file,
            )

            crane_photo = photo_service.finalize_crane_photo(
                session=session,
                photo_id=photo_id,
            )
            session.commit()

        except (PhotoStorageError, PhotoUploadRaceError) as e:
            session.rollback()
            _abandon_helper(session=session, photo_id=photo_id, crane_id=crane_id)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(e),
            )
        except SQLAlchemyError:
            session.rollback()
            _abandon_helper(session=session, photo_id=photo_id, crane_id=crane_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Photo could not be saved",
            )
    finally:
        photo.file.close()

    return serialize_crane_photo(crane_photo)


@crane_router.delete(
    "/{crane_id}/photos/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_crane_photo(
    session: SessionDep,
    crane_id: uuid.UUID,
    photo_id: uuid.UUID,
):
    photo_service.delete_crane_photo(
        session=session,
        crane_id=crane_id,
        photo_id=photo_id,
    )
    session.commit()
    logger.info(
        "crane_photo_delete_job_added",
        extra={"crane_id": str(crane_id), "photo_id": str(photo_id)},
    )


@crane_router.get("/photos", response_model=list[CranePhotoResponse])
def get_crane_photos(
    session: SessionDep, cursor: uuid.UUID | None = None, limit: int = 50
):
    photos = photo_service.get_crane_photos(
        session=session, photo_id=cursor, limit=limit
    )
    return PhotoListResponse(
        photos=[serialize_crane_photo(photo) for photo in photos],
        end=True if len(photos) < limit else False,
    )
