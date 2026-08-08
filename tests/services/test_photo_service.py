from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import select

from app.core.exceptions import (
    InvalidPhotoError,
    PhotoLimitExceededError,
    PhotoTooLargeError,
    ResourceNotFoundError,
    UnsupportedPhotoTypeError,
)
from app.models.base import (
    CranePhoto,
    CranePhotoStatus,
    JobOperation,
    JobStatus,
    OutboxJob,
    generate_uuid7,
)
from app.schemas.base import CraneInput
from app.services.crane import create_crane
from app.services.photo import (
    abandon_crane_photo_upload,
    delete_crane_photo,
    prepare_image,
    preupload_crane_photo,
)
from tests.utils.constants import SF_TEST_LAT, SF_TEST_LNG
from tests.utils.images import (
    TEST_EXIF_JPEG_BYTES,
    TEST_HEIF_BYTES,
    TEST_JPEG_BYTES,
    TEST_PNG_BYTES,
)
from tests.utils.photos import create_test_crane_photo


def make_solid_png(*, width: int, height: int) -> BytesIO:
    output = BytesIO()
    Image.new("1", (width, height)).save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


def test_prepare_image_rejects_oversized_long_edge():
    photo = make_solid_png(width=4097, height=1)

    with pytest.raises(PhotoTooLargeError, match="longest edge"):
        prepare_image(photo, "image/png")


def test_prepare_image_rejects_oversized_pixel_count():
    photo = make_solid_png(width=4001, height=4000)

    with pytest.raises(PhotoTooLargeError, match="16,000,000 pixels or fewer"):
        prepare_image(photo, "image/png")


def test_create_crane_photo_rejects_invalid_image_contents(session):
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=False,
    )

    with pytest.raises(InvalidPhotoError, match="not a valid image"):
        preupload_crane_photo(
            session=session,
            crane_id=crane.id,
            file=BytesIO(b"not really a JPEG"),
            filename="site.jpg",
            content_type="image/jpeg",
        )


def test_create_crane_photo_rejects_mismatched_image_type(session):
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=False,
    )

    with pytest.raises(UnsupportedPhotoTypeError, match="do not match"):
        preupload_crane_photo(
            session=session,
            crane_id=crane.id,
            file=BytesIO(TEST_PNG_BYTES),
            filename="site.jpg",
            content_type="image/jpeg",
        )


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
def test_create_crane_photo_rejects_invalid_photo(session, contents, content_type):
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=False,
    )
    with pytest.raises(InvalidPhotoError):
        preupload_crane_photo(
            session=session,
            crane_id=crane.id,
            file=BytesIO(contents),
            filename="site.jpg",
            content_type=content_type,
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

    photo = create_test_crane_photo(
        session=session,
        crane_id=crane.id,
        contents=TEST_EXIF_JPEG_BYTES,
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
    assert stored_photo.status == CranePhotoStatus.ACTIVE
    with Image.open(BytesIO(uploaded["contents"])) as sanitized:
        assert sanitized.format == "JPEG"
        assert len(sanitized.getexif()) == 0


def test_create_crane_photo_rejects_missing_crane(session):
    with pytest.raises(ResourceNotFoundError):
        preupload_crane_photo(
            session=session,
            crane_id=generate_uuid7(),
            file=BytesIO(TEST_JPEG_BYTES),
            filename="site.jpg",
            content_type="image/jpeg",
        )


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

    photo = create_test_crane_photo(
        session=session,
        crane_id=crane.id,
        contents=TEST_HEIF_BYTES,
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
        create_test_crane_photo(
            session=session,
            crane_id=crane.id,
            contents=TEST_JPEG_BYTES,
            filename=f"site-{photo_number}.jpg",
            content_type="image/jpeg",
        )

    with pytest.raises(PhotoLimitExceededError, match="at most 3"):
        preupload_crane_photo(
            session=session,
            crane_id=crane.id,
            file=BytesIO(TEST_JPEG_BYTES),
            filename="site-4.jpg",
            content_type="image/jpeg",
        )

    assert upload_count == 3


def test_create_crane_photo_rejects_fourth_photo_on_pending(session, monkeypatch):
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

    for photo_number in range(2):
        create_test_crane_photo(
            session=session,
            crane_id=crane.id,
            contents=TEST_JPEG_BYTES,
            filename=f"site-{photo_number}.jpg",
            content_type="image/jpeg",
        )

    photo, _ = preupload_crane_photo(
        session=session,
        crane_id=crane.id,
        file=BytesIO(TEST_JPEG_BYTES),
        filename="site-4.jpg",
        content_type="image/jpeg",
    )

    with pytest.raises(PhotoLimitExceededError, match="at most 3"):
        preupload_crane_photo(
            session=session,
            crane_id=crane.id,
            file=BytesIO(TEST_JPEG_BYTES),
            filename="site-4.jpg",
            content_type="image/jpeg",
        )

    assert upload_count == 2

    stored_photo = session.scalar(select(CranePhoto).where(CranePhoto.id == photo.id))
    assert stored_photo.status == CranePhotoStatus.PENDING_UPLOAD


def test_abandon_crane_photo_upload_succeeds(session, monkeypatch):
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=False,
    )

    monkeypatch.setattr(
        "app.services.storage.upload_photo",
        lambda file, *, object_key, content_type: None,
    )

    photo, _ = preupload_crane_photo(
        session=session,
        crane_id=crane.id,
        file=BytesIO(TEST_JPEG_BYTES),
        filename="site.jpg",
        content_type="image/jpeg",
    )

    abandon_crane_photo_upload(session=session, photo_id=photo.id)

    stored_photo = session.scalar(select(CranePhoto).where(CranePhoto.id == photo.id))
    assert stored_photo.status == CranePhotoStatus.PENDING_DELETE

    delete_job = session.scalar(
        select(OutboxJob).where(OutboxJob.storage_key == stored_photo.storage_key)
    )

    assert delete_job.status == JobStatus.PENDING
    assert delete_job.operation == JobOperation.DELETE


def test_abandon_crane_photo_upload_idempotent(session, monkeypatch):
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=False,
    )

    monkeypatch.setattr(
        "app.services.storage.upload_photo",
        lambda file, *, object_key, content_type: None,
    )

    photo, _ = preupload_crane_photo(
        session=session,
        crane_id=crane.id,
        file=BytesIO(TEST_JPEG_BYTES),
        filename="site.jpg",
        content_type="image/jpeg",
    )

    abandon_crane_photo_upload(session=session, photo_id=photo.id)
    abandon_crane_photo_upload(session=session, photo_id=photo.id)

    stored_photo = session.scalar(select(CranePhoto).where(CranePhoto.id == photo.id))
    assert stored_photo.status == CranePhotoStatus.PENDING_DELETE

    delete_jobs = session.scalars(
        select(OutboxJob).where(OutboxJob.storage_key == stored_photo.storage_key)
    ).all()

    assert len(delete_jobs) == 1


def test_abandon_crane_photo_upload_on_none_returns_clean(session):
    abandon_crane_photo_upload(session=session, photo_id=None)


def test_abandon_crane_photo_upload_on_missing_photo_returns_clean(
    session, monkeypatch
):
    abandon_crane_photo_upload(session=session, photo_id=generate_uuid7())


def test_delete_crane_photo_removes_creates_delete_job(session, monkeypatch):
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=False,
    )
    job_list = []
    monkeypatch.setattr(
        "app.services.storage.upload_photo",
        lambda file, *, object_key, content_type: (
            f"https://photos.example/{object_key}"
        ),
    )
    monkeypatch.setattr(
        "app.services.job.create_task",
        lambda session, *, operation, storage_key: job_list.append(
            (operation, storage_key)
        ),
    )
    photo = create_test_crane_photo(
        session=session,
        crane_id=crane.id,
        contents=TEST_JPEG_BYTES,
        filename="site.jpg",
        content_type="image/jpeg",
    )

    delete_crane_photo(session=session, crane_id=crane.id, photo_id=photo.id)

    op, key = job_list[0]
    assert op == JobOperation.DELETE
    assert key == f"cranes/{crane.id}/photos/{photo.id}.jpg"

    stored_photo = session.scalar(select(CranePhoto).where(CranePhoto.id == photo.id))
    assert stored_photo.status == CranePhotoStatus.PENDING_DELETE
