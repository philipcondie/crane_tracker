import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import PhotoStorageError
from app.models.base import CranePhoto, JobOperation, JobStatus, OutboxJob
from app.schemas.base import CraneInput
from app.services.crane import create_crane
from app.services.photo import delete_crane_photo
from app.worker.claim import claim_jobs
from app.worker.photo_jobs import (
    MAX_ATTEMPTS,
    MAX_DELAY,
    MIN_DELAY,
    calculate_backoff,
    run_delete_batch,
)
from tests.utils.constants import SF_TEST_LAT, SF_TEST_LNG
from tests.utils.images import (
    TEST_JPEG_BYTES,
)
from tests.utils.photos import create_test_crane_photo


@dataclass
class PhotoObj:
    crane_id: uuid.UUID
    photo_id: uuid.UUID
    storage_key: str


def fake_upload(file, *, object_key, content_type):
    return f"https://photos.example/{object_key}"


def test_claim_jobs_succeeds(session, monkeypatch):
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=True,
    )

    monkeypatch.setattr("app.services.storage.upload_photo", fake_upload)

    photo = create_test_crane_photo(
        session=session,
        crane_id=crane.id,
        contents=TEST_JPEG_BYTES,
        filename="site.jpg",
        content_type="image/jpeg",
    )

    storage_key = photo.storage_key

    delete_crane_photo(session=session, crane_id=crane.id, photo_id=photo.id)
    # Must commit prior transactions to allow claim to work with the func.now()
    session.commit()

    claimed_jobs = claim_jobs(session, JobOperation.DELETE, 5)
    assert len(claimed_jobs) == 1

    outbox_job = session.scalar(
        select(OutboxJob).where(OutboxJob.storage_key == storage_key)
    )
    assert outbox_job.status == JobStatus.PROCESSING
    assert outbox_job.attempts == 0
    assert outbox_job.lease_expires_at is not None


def test_claim_jobs_respects_leases(session, monkeypatch):
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=True,
    )

    monkeypatch.setattr("app.services.storage.upload_photo", fake_upload)

    photo = create_test_crane_photo(
        session=session,
        crane_id=crane.id,
        contents=TEST_JPEG_BYTES,
        filename="site.jpg",
        content_type="image/jpeg",
    )

    delete_crane_photo(session=session, crane_id=crane.id, photo_id=photo.id)
    # Must commit prior transactions to allow claim to work with the func.now()
    session.commit()

    # Claim job and set lease
    claim_jobs(session, JobOperation.DELETE, 5)
    time.sleep(2)
    reclaimed_jobs = claim_jobs(
        session=session, operation=JobOperation.DELETE, batch_size=5
    )
    assert len(reclaimed_jobs) == 0


def test_claim_jobs_succeeds_on_expired_lease(session, monkeypatch):
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=True,
    )

    monkeypatch.setattr("app.services.storage.upload_photo", fake_upload)

    photo = create_test_crane_photo(
        session=session,
        crane_id=crane.id,
        contents=TEST_JPEG_BYTES,
        filename="site.jpg",
        content_type="image/jpeg",
    )

    delete_crane_photo(session=session, crane_id=crane.id, photo_id=photo.id)
    # Must commit prior transactions to allow claim to work with the func.now()
    session.commit()

    monkeypatch.setattr("app.worker.claim.LOCK_LEASE_WINDOW", 1)
    # Claim job and set lease
    claim_jobs(session, JobOperation.DELETE, 5)
    time.sleep(2)
    reclaimed_jobs = claim_jobs(
        session=session, operation=JobOperation.DELETE, batch_size=5
    )
    assert len(reclaimed_jobs) == 1


@pytest.mark.parametrize("attempts", range(MAX_ATTEMPTS + 1))
def test_calculate_backoff_stays_within_ceiling(attempts):
    ceiling = min(MAX_DELAY, MIN_DELAY * (2**attempts))

    # Randomised, so sample rather than trusting a single draw.
    for _ in range(100):
        assert 0 <= calculate_backoff(attempts) <= ceiling


def test_calculate_backoff_ceiling_doubles_until_clamped(monkeypatch):
    # random.uniform(0, b) -> b exposes the ceiling for each attempt count.
    monkeypatch.setattr("app.worker.photo_jobs.random.uniform", lambda low, high: high)

    assert calculate_backoff(0) == MIN_DELAY
    assert calculate_backoff(1) == MIN_DELAY * 2
    assert calculate_backoff(2) == MIN_DELAY * 4
    assert calculate_backoff(3) == MIN_DELAY * 8


def test_calculate_backoff_clamps_at_max_delay(monkeypatch):
    monkeypatch.setattr("app.worker.photo_jobs.random.uniform", lambda low, high: high)

    # MIN_DELAY * 2**6 == 6400 already exceeds MAX_DELAY, so every
    # attempt count from here up must pin to the ceiling.
    for attempts in (6, 10, 100):
        assert calculate_backoff(attempts) == MAX_DELAY


def test_calculate_backoff_is_jittered():
    # Full jitter: repeated draws for the same attempt count must differ,
    # otherwise retries across workers would synchronise.
    draws = {calculate_backoff(4) for _ in range(50)}

    assert len(draws) > 1


def test_run_delete_batch_logs_only_on_sql_error(session, monkeypatch, caplog):
    def fake_claim(session, operation, batch_size):
        raise SQLAlchemyError()

    monkeypatch.setattr("app.worker.photo_jobs.claim_jobs", fake_claim)

    with caplog.at_level(logging.WARNING, logger="app.worker.photo_jobs"):
        run_delete_batch(session=session)

    assert "delete_batch_failed" in caplog.text


def test_run_delete_batch_succeeds(session, monkeypatch):
    # monkeypatch the storage_service.delete_photo
    # verify it captures success and deletes CranePhoto
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=True,
    )

    monkeypatch.setattr("app.services.storage.upload_photo", fake_upload)

    photo = create_test_crane_photo(
        session=session,
        crane_id=crane.id,
        contents=TEST_JPEG_BYTES,
        filename="site.jpg",
        content_type="image/jpeg",
    )

    photo_id = photo.id
    storage_key = photo.storage_key

    delete_crane_photo(session=session, crane_id=crane.id, photo_id=photo.id)
    # Must commit prior transactions to allow claim to work with the func.now()
    session.commit()

    deleted_keys = []

    def fake_delete(object_key):
        deleted_keys.append(object_key)

    monkeypatch.setattr("app.services.storage.delete_photo", fake_delete)

    run_delete_batch(session)

    # verify call made to storage to delete
    assert deleted_keys[0] == storage_key
    # verify job logged as success
    job = session.scalar(select(OutboxJob).where(OutboxJob.storage_key == storage_key))
    assert job.attempts == 1
    assert job.status == JobStatus.COMPLETED
    assert job.lease_expires_at is None

    photo_del = session.scalars(
        select(CranePhoto).where(CranePhoto.id == photo_id)
    ).one_or_none()
    assert photo_del is None


def test_run_delete_batch_captures_failure_below_max_attempts(session, monkeypatch):
    # monkey patch delete_photo to raise PhotoStorageError
    # verify it properly updates on failure
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=True,
    )

    monkeypatch.setattr("app.services.storage.upload_photo", fake_upload)

    photo = create_test_crane_photo(
        session=session,
        crane_id=crane.id,
        contents=TEST_JPEG_BYTES,
        filename="site.jpg",
        content_type="image/jpeg",
    )

    storage_key = photo.storage_key

    delete_crane_photo(session=session, crane_id=crane.id, photo_id=photo.id)
    # Must commit prior transactions to allow claim to work with the func.now()
    session.commit()

    def fake_delete(object_key):
        raise PhotoStorageError()

    monkeypatch.setattr("app.services.storage.delete_photo", fake_delete)
    monkeypatch.setattr(
        "app.worker.photo_jobs.calculate_backoff", lambda attempts: 2000
    )

    run_delete_batch(session)

    job = session.scalar(select(OutboxJob).where(OutboxJob.storage_key == storage_key))
    assert job.attempts == 1
    assert job.status == JobStatus.PENDING
    assert job.lease_expires_at is None
    assert job.last_error is not None

    time_delta = job.available_at.replace(tzinfo=UTC) - datetime.now(tz=UTC)
    print(f"Delta: {time_delta}")
    assert time_delta < timedelta(milliseconds=2500)


def test_run_delete_batch_captures_failure_at_max_attempts(session, monkeypatch):
    # monkey patch delete_photo to raise PhotoStorageError,
    # verify it properly updates on failure
    crane = create_crane(
        session=session,
        input=CraneInput(lat=SF_TEST_LAT, lng=SF_TEST_LNG),
        override_duplicate_warning=True,
    )

    monkeypatch.setattr("app.services.storage.upload_photo", fake_upload)

    photo = create_test_crane_photo(
        session=session,
        crane_id=crane.id,
        contents=TEST_JPEG_BYTES,
        filename="site.jpg",
        content_type="image/jpeg",
    )

    storage_key = photo.storage_key

    delete_crane_photo(session=session, crane_id=crane.id, photo_id=photo.id)
    # Must commit prior transactions to allow claim to work with the func.now()
    session.commit()

    def fake_delete(object_key):
        raise PhotoStorageError()

    monkeypatch.setattr("app.services.storage.delete_photo", fake_delete)
    monkeypatch.setattr(
        "app.worker.photo_jobs.calculate_backoff", lambda attempts: 2000
    )
    monkeypatch.setattr("app.worker.photo_jobs.MAX_ATTEMPTS", 1)

    run_delete_batch(session)

    job = session.scalar(select(OutboxJob).where(OutboxJob.storage_key == storage_key))
    assert job.attempts == 1
    assert job.status == JobStatus.FAILED


# what other cases?
