import uuid
from io import BytesIO

from sqlalchemy.orm import Session

from app.models.base import CranePhoto
from app.services.photo import (
    finalize_crane_photo,
    preflight_crane_photo,
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
    preflight_crane_photo(session=session, crane_id=crane_id)
    session.commit()
    uploaded_photo = upload_crane_photo_to_storage(
        crane_id=crane_id,
        file=BytesIO(contents),
        filename=filename,
        content_type=content_type,
    )
    photo = finalize_crane_photo(
        session=session,
        uploaded_photo=uploaded_photo,
    )
    session.commit()
    return photo
