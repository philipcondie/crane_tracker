import time
import uuid
from dataclasses import dataclass
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.models.base import (
    CranePhoto,
    CranePhotoStatus,
    OutboxJob,
)
from app.schemas.base import CraneInput
from app.services.crane import create_crane
from app.services.photo import preupload_crane_photo
from app.worker.photo_jobs import run_reap_crane_photos
from tests.utils.constants import SF_TEST_LAT, SF_TEST_LNG
from tests.utils.images import (
    TEST_JPEG_BYTES,
)


@dataclass
class PhotoObj:
    crane_id: uuid.UUID
    photo_id: uuid.UUID
    storage_key: str


def test_reap_crane_photos_ignores_recent(session):
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=True,
    )

    photo, _ = preupload_crane_photo(
        session=session,
        crane_id=crane.id,
        file=BytesIO(TEST_JPEG_BYTES),
        filename="site.jpg",
        content_type="image/jpeg",
    )

    photo_id = photo.id
    storage_key = photo.storage_key

    session.commit()

    run_reap_crane_photos(session=session)

    # verify photo status is still pending and no job was created
    photo = session.scalar(select(CranePhoto).where(CranePhoto.id == photo_id))
    assert photo.status == CranePhotoStatus.PENDING_UPLOAD

    job = session.scalar(select(OutboxJob).where(OutboxJob.storage_key == storage_key))
    assert job is None


def test_reap_crane_photos_succeeds(session, monkeypatch):
    monkeypatch.setattr("app.worker.photo_jobs.PENDING_UPLOAD_WINDOW", 1)
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=True,
    )

    photo, _ = preupload_crane_photo(
        session=session,
        crane_id=crane.id,
        file=BytesIO(TEST_JPEG_BYTES),
        filename="site.jpg",
        content_type="image/jpeg",
    )

    photo_id = photo.id
    storage_key = photo.storage_key

    session.commit()
    time.sleep(0.5)
    run_reap_crane_photos(session=session)

    # verify photo status is still pending and no job was created
    photo = session.scalar(select(CranePhoto).where(CranePhoto.id == photo_id))
    assert photo.status == CranePhotoStatus.PENDING_DELETE

    job = session.scalar(select(OutboxJob).where(OutboxJob.storage_key == storage_key))
    assert job is not None


def test_reap_crane_photos_fails_after_error(session, monkeypatch):
    monkeypatch.setattr("app.worker.photo_jobs.PENDING_UPLOAD_WINDOW", 1)

    crane_1 = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=True,
    )

    crane_2 = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=True,
    )

    photo_1, _ = preupload_crane_photo(
        session=session,
        crane_id=crane_1.id,
        file=BytesIO(TEST_JPEG_BYTES),
        filename="site.jpg",
        content_type="image/jpeg",
    )

    photo_2, _ = preupload_crane_photo(
        session=session,
        crane_id=crane_2.id,
        file=BytesIO(TEST_JPEG_BYTES),
        filename="site.jpg",
        content_type="image/jpeg",
    )

    photo_obj_1 = PhotoObj(
        crane_id=crane_1.id, photo_id=photo_1.id, storage_key=photo_1.storage_key
    )
    photo_obj_2 = PhotoObj(
        crane_id=crane_2.id, photo_id=photo_2.id, storage_key=photo_2.storage_key
    )

    session.commit()
    time.sleep(0.1)

    def fake_create_delete_crane_job(session, *, photo):
        raise SQLAlchemyError()

    monkeypatch.setattr(
        "app.worker.photo_jobs.photo_service.create_delete_crane_job",
        fake_create_delete_crane_job,
    )
    run_reap_crane_photos(session)

    photo_1 = session.scalar(
        select(CranePhoto).where(CranePhoto.id == photo_obj_1.photo_id)
    )
    photo_2 = session.scalar(
        select(CranePhoto).where(CranePhoto.id == photo_obj_2.photo_id)
    )

    assert photo_1.status == CranePhotoStatus.PENDING_UPLOAD
    assert photo_2.status == CranePhotoStatus.PENDING_UPLOAD

    job_1 = session.scalar(
        select(OutboxJob).where(OutboxJob.storage_key == photo_obj_1.storage_key)
    )
    assert job_1 is None
    job_2 = session.scalar(
        select(OutboxJob).where(OutboxJob.storage_key == photo_obj_2.storage_key)
    )
    assert job_2 is None


def test_reap_crane_photos_idempotent(session, monkeypatch):
    monkeypatch.setattr("app.worker.photo_jobs.PENDING_UPLOAD_WINDOW", 1)
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=True,
    )

    photo, _ = preupload_crane_photo(
        session=session,
        crane_id=crane.id,
        file=BytesIO(TEST_JPEG_BYTES),
        filename="site.jpg",
        content_type="image/jpeg",
    )

    storage_key = photo.storage_key

    session.commit()
    time.sleep(0.5)
    run_reap_crane_photos(session=session)
    run_reap_crane_photos(session=session)

    jobs = session.scalars(
        select(OutboxJob).where(OutboxJob.storage_key == storage_key)
    ).all()

    assert len(jobs) == 1
