import uuid
from io import BytesIO

from sqlalchemy.orm import Session

from app.models.base import CranePhoto
from app.services.photo import (
    finalize_crane_photo,
    preupload_crane_photo,
    upload_crane_photo_to_storage,
)
from tests.utils.images import TEST_JPEG_BYTES


def create_test_crane_photo(
    session: Session,
    *,
    crane_id: uuid.UUID,
    contents: bytes = TEST_JPEG_BYTES,
    filename: str = "site.jpg",
    content_type: str = "image/jpeg",
) -> CranePhoto:
    crane_photo, prepared_file = preupload_crane_photo(
        session=session,
        crane_id=crane_id,
        file=BytesIO(contents),
        filename=filename,
        content_type=content_type,
    )
    session.commit()
    photo_id = crane_photo.id
    storage_key = crane_photo.storage_key
    content_type = crane_photo.content_type

    upload_crane_photo_to_storage(
        photo_id=photo_id,
        crane_id=crane_id,
        storage_key=storage_key,
        content_type=content_type,
        file=prepared_file,
    )
    photo = finalize_crane_photo(session=session, photo_id=photo_id)
    session.commit()
    return photo
