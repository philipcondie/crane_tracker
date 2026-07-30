from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import (
    InvalidPhotoError,
    PhotoLimitExceededError,
    ResourceNotFoundError,
    UnsupportedPhotoTypeError,
)
from app.models.base import CranePhoto, generate_uuid7
from app.schemas.base import CraneInput
from app.services.crane import create_crane
from app.services.photo import create_crane_photo, delete_crane_photo
from tests.utils.constants import SF_TEST_LAT, SF_TEST_LNG
from tests.utils.images import (
    TEST_EXIF_JPEG_BYTES,
    TEST_HEIF_BYTES,
    TEST_JPEG_BYTES,
    TEST_PNG_BYTES,
)


def test_create_crane_photo_strips_metadata_and_persists_record(session, monkeypatch):
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=False,
    )
    uploaded = {}

    def fake_upload(file, *, object_key, content_type):
        uploaded["contents"] = file.read()
        uploaded["object_key"] = object_key
        uploaded["content_type"] = content_type
        return f"https://photos.example/{object_key}"

    monkeypatch.setattr("app.services.storage.upload_photo", fake_upload)

    photo = create_crane_photo(
        session=session,
        crane_id=crane.id,
        file=BytesIO(TEST_EXIF_JPEG_BYTES),
        filename="site.jpg",
        content_type="image/jpeg",
    )

    stored_photo = session.scalar(select(CranePhoto).where(CranePhoto.id == photo.id))
    assert stored_photo is not None
    assert stored_photo.crane_id == crane.id
    assert stored_photo.original_filename == "site.jpg"
    assert stored_photo.storage_key == photo.storage_key
    assert uploaded["object_key"] == photo.storage_key
    assert uploaded["content_type"] == "image/jpeg"
    assert uploaded["contents"] != TEST_EXIF_JPEG_BYTES
    with Image.open(BytesIO(uploaded["contents"])) as sanitized:
        assert sanitized.format == "JPEG"
        assert len(sanitized.getexif()) == 0


def test_create_crane_photo_rejects_missing_crane(session, monkeypatch):
    upload_called = False

    def fake_upload(file, *, object_key, content_type):
        nonlocal upload_called
        upload_called = True

    monkeypatch.setattr("app.services.storage.upload_photo", fake_upload)

    with pytest.raises(ResourceNotFoundError):
        create_crane_photo(
            session=session,
            crane_id=generate_uuid7(),
            file=BytesIO(TEST_JPEG_BYTES),
            filename="site.jpg",
            content_type="image/jpeg",
        )

    assert upload_called is False


def test_create_crane_photo_converts_heic_to_jpeg(session, monkeypatch):
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=False,
    )
    uploaded = {}

    def fake_upload(file, *, object_key, content_type):
        uploaded["contents"] = file.read()
        uploaded["object_key"] = object_key
        uploaded["content_type"] = content_type

    monkeypatch.setattr("app.services.storage.upload_photo", fake_upload)

    photo = create_crane_photo(
        session=session,
        crane_id=crane.id,
        file=BytesIO(TEST_HEIF_BYTES),
        filename="site.heic",
        content_type="image/heic",
    )

    assert photo.content_type == "image/jpeg"
    assert uploaded["content_type"] == "image/jpeg"
    assert uploaded["object_key"].endswith(".jpg")
    with Image.open(BytesIO(uploaded["contents"])) as converted:
        assert converted.format == "JPEG"
        assert len(converted.getexif()) == 0


def test_create_crane_photo_rejects_fourth_photo(session, monkeypatch):
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=False,
    )
    upload_count = 0

    def fake_upload(file, *, object_key, content_type):
        nonlocal upload_count
        upload_count += 1
        return f"https://photos.example/{object_key}"

    monkeypatch.setattr("app.services.storage.upload_photo", fake_upload)

    for photo_number in range(3):
        create_crane_photo(
            session=session,
            crane_id=crane.id,
            file=BytesIO(TEST_JPEG_BYTES),
            filename=f"site-{photo_number}.jpg",
            content_type="image/jpeg",
        )

    with pytest.raises(PhotoLimitExceededError, match="at most 3"):
        create_crane_photo(
            session=session,
            crane_id=crane.id,
            file=BytesIO(TEST_JPEG_BYTES),
            filename="site-4.jpg",
            content_type="image/jpeg",
        )

    assert upload_count == 3


def test_create_crane_photo_rejects_invalid_image_contents(session, monkeypatch):
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=False,
    )
    upload_called = False

    def fake_upload(file, *, object_key, content_type):
        nonlocal upload_called
        upload_called = True

    monkeypatch.setattr("app.services.storage.upload_photo", fake_upload)

    with pytest.raises(InvalidPhotoError, match="not a valid image"):
        create_crane_photo(
            session=session,
            crane_id=crane.id,
            file=BytesIO(b"not really a JPEG"),
            filename="site.jpg",
            content_type="image/jpeg",
        )

    assert upload_called is False


def test_create_crane_photo_rejects_mismatched_image_type(session, monkeypatch):
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=False,
    )

    with pytest.raises(UnsupportedPhotoTypeError, match="do not match"):
        create_crane_photo(
            session=session,
            crane_id=crane.id,
            file=BytesIO(TEST_PNG_BYTES),
            filename="site.jpg",
            content_type="image/jpeg",
        )


def test_create_crane_photo_cleans_up_r2_when_database_flush_fails(
    session, monkeypatch
):
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=False,
    )
    deleted_keys = []

    monkeypatch.setattr(
        "app.services.storage.upload_photo",
        lambda file, *, object_key, content_type: (
            f"https://photos.example/{object_key}"
        ),
    )
    monkeypatch.setattr(
        "app.services.storage.delete_photo",
        lambda *, object_key: deleted_keys.append(object_key),
    )
    original_flush = session.flush

    def fail_photo_flush(*args, **kwargs):
        if any(isinstance(record, CranePhoto) for record in session.new):
            raise SQLAlchemyError("flush failed")
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(session, "flush", fail_photo_flush)

    with pytest.raises(SQLAlchemyError, match="flush failed"):
        create_crane_photo(
            session=session,
            crane_id=crane.id,
            file=BytesIO(TEST_JPEG_BYTES),
            filename="site.jpg",
            content_type="image/jpeg",
        )

    assert len(deleted_keys) == 1
    assert deleted_keys[0].startswith(f"cranes/{crane.id}/photos/")
    session.rollback()


def test_delete_crane_photo_removes_r2_object_and_database_record(session, monkeypatch):
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=False,
    )
    deleted_keys = []
    monkeypatch.setattr(
        "app.services.storage.upload_photo",
        lambda file, *, object_key, content_type: (
            f"https://photos.example/{object_key}"
        ),
    )
    monkeypatch.setattr(
        "app.services.storage.delete_photo",
        lambda *, object_key: deleted_keys.append(object_key),
    )
    photo = create_crane_photo(
        session=session,
        crane_id=crane.id,
        file=BytesIO(TEST_JPEG_BYTES),
        filename="site.jpg",
        content_type="image/jpeg",
    )

    delete_crane_photo(session=session, crane_id=crane.id, photo_id=photo.id)

    assert deleted_keys == [photo.storage_key]
    assert session.get(CranePhoto, photo.id) is None


def test_delete_crane_photo_rejects_missing_photo(session, monkeypatch):
    with pytest.raises(ResourceNotFoundError):
        delete_crane_photo(
            session=session,
            crane_id=generate_uuid7(),
            photo_id=generate_uuid7(),
        )


@pytest.mark.parametrize(
    "contents,content_type",
    [
        (b"", "image/jpeg"),
        (b"not an image", "text/plain"),
    ],
)
def test_create_crane_photo_rejects_invalid_photo(
    session, monkeypatch, contents, content_type
):
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=False,
    )
    upload_called = False

    def fake_upload(file, *, object_key, content_type):
        nonlocal upload_called
        upload_called = True

    monkeypatch.setattr("app.services.storage.upload_photo", fake_upload)

    with pytest.raises(InvalidPhotoError):
        create_crane_photo(
            session=session,
            crane_id=crane.id,
            file=BytesIO(contents),
            filename="site.jpg",
            content_type=content_type,
        )

    assert upload_called is False
