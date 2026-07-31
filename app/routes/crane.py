import uuid

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError

import app.services.crane as crane_service
import app.services.photo as photo_service
import app.services.storage as storage_service
from app.core.config import get_settings
from app.core.dependencies import SessionDep
from app.core.exceptions import (
    DuplicateCraneError,
    DuplicateGoneReportError,
    InvalidCoordinateError,
    InvalidPhotoError,
    PhotoLimitExceededError,
    PhotoStorageError,
    PhotoTooLargeError,
    ResourceNotFoundError,
    UnsupportedPhotoTypeError,
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
)

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
    try:
        crane = crane_service.create_crane(
            session=session,
            input=crane_input,
            override_duplicate_warning=create_request.override_duplicate_warning,
        )
    except DuplicateCraneError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    session.commit()
    return crane


@crane_router.get("/{crane_id}", response_model=CraneDetail)
def get_crane(session: SessionDep, crane_id: uuid.UUID):
    try:
        crane = crane_service.get_crane(session=session, id=crane_id)
        photo_items = [serialize_crane_photo(photo) for photo in crane.photo_records]
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PhotoStorageError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return cranes


@crane_router.post("/{crane_id}/report")
def report_crane_as_gone(session: SessionDep, crane_id: uuid.UUID, request: Request):
    client_ip = request.client.host if request.client else None

    if client_ip is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="could not identify host to record report",
        )

    try:
        crane_service.report_crane_as_gone(
            session=session, crane_id=crane_id, client_ip=client_ip
        )
        session.commit()
    except ResourceNotFoundError as e:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DuplicateGoneReportError as e:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


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
    uploaded_photo = None
    crane_photo = None

    def cleanup_after_rollback() -> None:
        if uploaded_photo is not None:
            photo_service.cleanup_uploaded_photo(object_key=uploaded_photo.storage_key)

    try:
        photo_service.preflight_crane_photo(session=session, crane_id=crane_id)
        session.commit()  # required to close out transaction before next steps

        uploaded_photo = photo_service.upload_crane_photo_to_storage(
            crane_id=crane_id,
            file=photo.file,
            filename=photo.filename or "photo",
            content_type=photo.content_type or "application/octet-stream",
        )
        crane_photo = photo_service.finalize_crane_photo(
            session=session,
            uploaded_photo=uploaded_photo,
        )
        session.commit()
    except ResourceNotFoundError as e:
        session.rollback()
        cleanup_after_rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PhotoLimitExceededError as e:
        session.rollback()
        cleanup_after_rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except PhotoTooLargeError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(e),
        )
    except UnsupportedPhotoTypeError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(e),
        )
    except InvalidPhotoError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        )
    except PhotoStorageError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except SQLAlchemyError:
        session.rollback()
        cleanup_after_rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Photo metadata could not be saved",
        )
    finally:
        photo.file.close()

    return serialize_crane_photo(crane_photo)


# TODO: Re-enable this route after adding admin-level authorization.
# @crane_router.delete(
#     "/{crane_id}/photos/{photo_id}",
#     status_code=status.HTTP_204_NO_CONTENT,
# )
# def delete_crane_photo(
#     session: SessionDep,
#     crane_id: uuid.UUID,
#     photo_id: uuid.UUID,
# ):
#     try:
#         photo_service.delete_crane_photo(
#             session=session,
#             crane_id=crane_id,
#             photo_id=photo_id,
#         )
#         session.commit()
#     except ResourceNotFoundError as e:
#         session.rollback()
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
#     except PhotoStorageError as e:
#         session.rollback()
#         raise HTTPException(
#             status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
#             detail=str(e),
#         )
