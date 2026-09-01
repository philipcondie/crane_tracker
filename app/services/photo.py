import logging
import uuid
import warnings
from io import BytesIO
from typing import BinaryIO

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

import app.services.job as job_service
import app.services.storage as storage_service
from app.core.exceptions import (
    InvalidPhotoError,
    PhotoLimitExceededError,
    PhotoTooLargeError,
    PhotoUploadRaceError,
    ResourceNotFoundError,
    UnsupportedPhotoTypeError,
)
from app.models.base import (
    Crane,
    CranePhoto,
    CranePhotoStatus,
    JobOperation,
    generate_uuid7,
)

logger = logging.getLogger(__name__)

register_heif_opener()

MAX_PHOTO_SIZE_BYTES = 10 * 1024 * 1024
MAX_PHOTO_PIXELS = 16_000_000
MAX_PHOTO_LONG_EDGE_PIXELS = 4096
MAX_PHOTOS_PER_CRANE = 3
IMAGE_FORMATS = {
    "HEIF": ({"image/heic", "image/heif"}, "JPEG", "image/jpeg", ".jpg"),
    "JPEG": ({"image/jpeg"}, "JPEG", "image/jpeg", ".jpg"),
    "PNG": ({"image/png"}, "PNG", "image/png", ".png"),
    "WEBP": ({"image/webp"}, "WEBP", "image/webp", ".webp"),
}
ALLOWED_PHOTO_TYPES = {
    content_type
    for content_types, _, _, _ in IMAGE_FORMATS.values()
    for content_type in content_types
}


def create_storage_key(crane_id: uuid.UUID, photo_id: uuid.UUID, extension: str):
    return f"cranes/{crane_id}/photos/{photo_id}{extension}"


def prepare_image(
    file: BinaryIO,
    content_type: str,
) -> tuple[BytesIO, str, str]:
    """Verify and re-encode an image without EXIF or other source metadata."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(file) as image:
                image_format = image.format
                width, height = image.size
                if max(width, height) > MAX_PHOTO_LONG_EDGE_PIXELS:
                    raise PhotoTooLargeError(
                        "Photo longest edge must be "
                        f"{MAX_PHOTO_LONG_EDGE_PIXELS:,} pixels or fewer"
                    )
                if width * height > MAX_PHOTO_PIXELS:
                    raise PhotoTooLargeError(
                        f"Photo must contain {MAX_PHOTO_PIXELS:,} pixels or fewer"
                    )
                image.verify()
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        ValueError,
    ) as e:
        raise InvalidPhotoError("File is not a valid image") from e
    finally:
        file.seek(0)

    format_config = IMAGE_FORMATS.get(image_format or "")
    if format_config is None or content_type not in format_config[0]:
        raise UnsupportedPhotoTypeError(
            "Photo contents do not match the declared content type"
        )

    output_format, output_content_type, extension = format_config[1:]
    output = BytesIO()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(file) as source:
                processed = ImageOps.exif_transpose(source).copy()
                processed.info.clear()
                if output_format == "JPEG":
                    processed = processed.convert("RGB")
                    processed.save(output, format="JPEG", quality=90, optimize=True)
                elif output_format == "PNG":
                    processed.save(output, format="PNG", optimize=True)
                else:
                    if processed.mode not in ("RGB", "RGBA"):
                        processed = processed.convert("RGBA")
                    processed.save(output, format="WEBP", quality=90, method=4)
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        ValueError,
    ) as e:
        raise InvalidPhotoError("File could not be safely processed") from e
    finally:
        file.seek(0)

    if output.tell() > MAX_PHOTO_SIZE_BYTES:
        raise PhotoTooLargeError("Processed photo must be 10 MB or smaller")
    output.seek(0)
    return output, output_content_type, extension


def ensure_crane_photo_capacity(
    session: Session,
    *,
    crane_id: uuid.UUID,
    lock_crane: bool,
) -> None:
    crane_query = select(Crane.id).where(Crane.id == crane_id)
    if lock_crane:
        crane_query = crane_query.with_for_update()

    crane_exists = session.scalar(crane_query)
    if crane_exists is None:
        raise ResourceNotFoundError(resource="crane", identifier=str(crane_id))

    active_photo_count = session.scalar(
        select(func.count(CranePhoto.id)).where(
            CranePhoto.crane_id == crane_id,
            or_(
                CranePhoto.status == CranePhotoStatus.ACTIVE,
                CranePhoto.status == CranePhotoStatus.PENDING_UPLOAD,
            ),
        )
    )
    if active_photo_count >= MAX_PHOTOS_PER_CRANE:
        raise PhotoLimitExceededError(
            f"A crane can have at most {MAX_PHOTOS_PER_CRANE} photos",
            crane_id=crane_id,
            active_photo_count=active_photo_count,
        )


def preupload_crane_photo(
    session: Session,
    *,
    crane_id: uuid.UUID,
    file: BinaryIO,
    filename: str,
    content_type: str,
) -> tuple[CranePhoto, BytesIO]:
    """Validate the photo and add to database before upload"""
    if content_type not in ALLOWED_PHOTO_TYPES:
        raise UnsupportedPhotoTypeError(
            f"Unsupported photo content type: {content_type}"
        )
    if len(filename) > 255:
        raise InvalidPhotoError("Photo filename must be 255 characters or fewer")

    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    if file_size == 0:
        raise InvalidPhotoError("Photo must not be empty")
    if file_size > MAX_PHOTO_SIZE_BYTES:
        raise PhotoTooLargeError("Photo must be 10 MB or smaller")

    prepared_file, stored_content_type, extension = prepare_image(file, content_type)

    ensure_crane_photo_capacity(session=session, crane_id=crane_id, lock_crane=True)
    photo_id = generate_uuid7()
    storage_key = create_storage_key(
        crane_id=crane_id, photo_id=photo_id, extension=extension
    )

    photo = CranePhoto(
        id=photo_id,
        crane_id=crane_id,
        storage_key=storage_key,
        original_filename=filename,
        content_type=stored_content_type,
    )

    session.add(photo)
    session.flush()

    logger.info(
        "crane_photo_created",
        extra={"crane_id": str(photo.crane_id), "photo_id": str(photo.id)},
    )

    return photo, prepared_file


def upload_crane_photo_to_storage(
    *,
    photo_id: uuid.UUID,
    crane_id: uuid.UUID,
    storage_key: str,
    content_type: str,
    file: BinaryIO,
) -> None:
    """Upload a photo without a database transaction."""

    storage_service.upload_photo(
        file,
        object_key=storage_key,
        content_type=content_type,
    )

    logger.info(
        "crane_photo_uploaded",
        extra={"crane_id": str(crane_id), "photo_id": str(photo_id)},
    )


def finalize_crane_photo(
    session: Session,
    *,
    photo_id: uuid.UUID,
) -> CranePhoto:
    """Update the photo status for successful upload"""
    crane_photo = session.scalars(
        update(CranePhoto)
        .where(
            CranePhoto.id == photo_id,
            CranePhoto.status == CranePhotoStatus.PENDING_UPLOAD,
        )
        .values(status=CranePhotoStatus.ACTIVE)
        .returning(CranePhoto)
    ).one_or_none()
    if crane_photo is None:
        raise PhotoUploadRaceError()

    logger.info(
        "crane_photo_activated",
        extra={"crane_id": str(crane_photo.crane_id), "photo_id": str(crane_photo.id)},
    )
    return crane_photo


def create_delete_crane_job(session: Session, *, photo: CranePhoto):
    photo.status = CranePhotoStatus.PENDING_DELETE
    job_service.create_task(
        session=session, operation=JobOperation.DELETE, storage_key=photo.storage_key
    )


def abandon_crane_photo_upload(session: Session, *, photo_id: uuid.UUID | None) -> None:
    if photo_id is None:
        return
    photo = session.scalar(
        select(CranePhoto).where(
            CranePhoto.id == photo_id,
            CranePhoto.status == CranePhotoStatus.PENDING_UPLOAD,
        )
    )
    if photo is None:
        return

    create_delete_crane_job(session=session, photo=photo)


def delete_crane_photo(
    session: Session,
    *,
    crane_id: uuid.UUID,
    photo_id: uuid.UUID,
) -> None:
    photo = session.scalar(
        select(CranePhoto).where(
            CranePhoto.id == photo_id,
            CranePhoto.crane_id == crane_id,
            CranePhoto.status == CranePhotoStatus.ACTIVE,
        )
    )

    if photo is None:
        raise ResourceNotFoundError(resource="photo", identifier=str(photo_id))

    create_delete_crane_job(session=session, photo=photo)
