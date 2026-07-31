import logging
import uuid
import warnings
from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.services.storage as storage_service
from app.core.exceptions import (
    InvalidPhotoError,
    PhotoLimitExceededError,
    PhotoStorageError,
    PhotoTooLargeError,
    ResourceNotFoundError,
    UnsupportedPhotoTypeError,
)
from app.models.base import Crane, CranePhoto, generate_uuid7

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


def cleanup_uploaded_photo(*, object_key: str) -> None:
    """Best-effort removal used when database persistence fails."""
    try:
        storage_service.delete_photo(object_key=object_key)
    except PhotoStorageError:
        logger.warning(
            "crane_photo_cleanup_failed",
            extra={"object_key": object_key},
        )


@dataclass(frozen=True)
class UploadedCranePhoto:
    id: uuid.UUID
    crane_id: uuid.UUID
    storage_key: str
    original_filename: str
    content_type: str


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
        logger.warning(
            "crane_photo_create_failed",
            extra={"crane_id": str(crane_id), "reason": "crane_not_found"},
        )
        raise ResourceNotFoundError(resource="crane", identifier=str(crane_id))

    photo_count = session.scalar(
        select(func.count(CranePhoto.id)).where(CranePhoto.crane_id == crane_id)
    )
    if photo_count >= MAX_PHOTOS_PER_CRANE:
        logger.warning(
            "crane_photo_create_failed",
            extra={
                "crane_id": str(crane_id),
                "photo_count": photo_count,
                "reason": "photo_limit_exceeded",
            },
        )
        raise PhotoLimitExceededError(
            f"A crane can have at most {MAX_PHOTOS_PER_CRANE} photos"
        )


def preflight_crane_photo(session: Session, *, crane_id: uuid.UUID) -> None:
    """Check existence and capacity without taking a row lock."""
    ensure_crane_photo_capacity(
        session=session,
        crane_id=crane_id,
        lock_crane=False,
    )


def upload_crane_photo_to_storage(
    *,
    crane_id: uuid.UUID,
    file: BinaryIO,
    filename: str,
    content_type: str,
) -> UploadedCranePhoto:
    """Validate, process, and upload a photo without a database transaction."""
    if content_type not in ALLOWED_PHOTO_TYPES:
        logger.warning(
            "crane_photo_create_failed",
            extra={
                "crane_id": str(crane_id),
                "content_type": content_type,
                "reason": "unsupported_content_type",
            },
        )
        raise UnsupportedPhotoTypeError(
            f"Unsupported photo content type: {content_type}"
        )
    if len(filename) > 255:
        logger.warning(
            "crane_photo_create_failed",
            extra={"crane_id": str(crane_id), "reason": "filename_too_long"},
        )
        raise InvalidPhotoError("Photo filename must be 255 characters or fewer")

    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    if file_size == 0:
        logger.warning(
            "crane_photo_create_failed",
            extra={"crane_id": str(crane_id), "reason": "empty_photo"},
        )
        raise InvalidPhotoError("Photo must not be empty")
    if file_size > MAX_PHOTO_SIZE_BYTES:
        logger.warning(
            "crane_photo_create_failed",
            extra={
                "crane_id": str(crane_id),
                "file_size": file_size,
                "reason": "photo_too_large",
            },
        )
        raise PhotoTooLargeError("Photo must be 10 MB or smaller")

    prepared_file, stored_content_type, extension = prepare_image(file, content_type)
    photo_id = generate_uuid7()
    object_key = f"cranes/{crane_id}/photos/{photo_id}{extension}"
    storage_service.upload_photo(
        prepared_file,
        object_key=object_key,
        content_type=stored_content_type,
    )

    logger.info(
        "crane_photo_uploaded",
        extra={"crane_id": str(crane_id), "photo_id": str(photo_id)},
    )
    return UploadedCranePhoto(
        id=photo_id,
        crane_id=crane_id,
        storage_key=object_key,
        original_filename=filename,
        content_type=stored_content_type,
    )


def finalize_crane_photo(
    session: Session,
    *,
    uploaded_photo: UploadedCranePhoto,
) -> CranePhoto:
    """Recheck capacity under a short row lock and persist photo metadata."""
    ensure_crane_photo_capacity(
        session=session,
        crane_id=uploaded_photo.crane_id,
        lock_crane=True,
    )

    photo = CranePhoto(
        id=uploaded_photo.id,
        crane_id=uploaded_photo.crane_id,
        storage_key=uploaded_photo.storage_key,
        original_filename=uploaded_photo.original_filename,
        content_type=uploaded_photo.content_type,
    )
    session.add(photo)
    session.flush()
    session.refresh(photo)

    logger.info(
        "crane_photo_created",
        extra={"crane_id": str(photo.crane_id), "photo_id": str(photo.id)},
    )
    return photo


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
        )
    )
    if photo is None:
        logger.warning(
            "crane_photo_delete_failed",
            extra={
                "crane_id": str(crane_id),
                "photo_id": str(photo_id),
                "reason": "photo_not_found",
            },
        )
        raise ResourceNotFoundError(resource="photo", identifier=str(photo_id))

    storage_service.delete_photo(object_key=photo.storage_key)
    session.delete(photo)
    session.flush()
    logger.info(
        "crane_photo_deleted",
        extra={"crane_id": str(crane_id), "photo_id": str(photo_id)},
    )
