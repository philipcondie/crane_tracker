import logging
import random
import threading
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import and_, delete, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import app.services.photo as photo_service
import app.services.storage as storage_service
from app.core.config import get_settings
from app.core.exceptions import PhotoStorageError, ResourceNotFoundError
from app.models.base import (
    CranePhoto,
    CranePhotoStatus,
    JobOperation,
    JobStatus,
    OutboxJob,
)

settings = get_settings()
logger = logging.getLogger(__name__)

JOB_BATCH_SIZE = settings.job_batch_size
MAX_ATTEMPTS = 5
MIN_DELAY = 100  # ms
MAX_DELAY = 4000  # ms
PENDING_UPLOAD_WINDOW = 5000  # ms
LOCK_LEASE_WINDOW = 300


@dataclass
class ClaimedJob:
    id: uuid.UUID
    operation: JobOperation
    storage_key: str


def claim_jobs(
    session: Session, operation: JobOperation, batch_size: int
) -> list[ClaimedJob]:
    query = (
        select(OutboxJob)
        .where(
            and_(
                OutboxJob.operation == operation,
                or_(
                    and_(
                        OutboxJob.status == JobStatus.PENDING,
                        OutboxJob.available_at < func.now(),
                    ),
                    and_(
                        OutboxJob.status == JobStatus.PROCESSING,
                        OutboxJob.lease_expires_at < func.now(),
                    ),
                ),
            )
        )
        .order_by(OutboxJob.created_at)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )

    jobs = session.scalars(query).all()

    claimed_jobs = []
    for job in jobs:
        job.status = JobStatus.PROCESSING
        job.lease_expires_at = func.now() + text(
            f"INTERVAL '{LOCK_LEASE_WINDOW} SECONDS'"
        )

        claimed_job = ClaimedJob(
            id=job.id, operation=job.operation, storage_key=job.storage_key
        )
        claimed_jobs.append(claimed_job)

    session.commit()

    return claimed_jobs


def calculate_backoff(attempts: int) -> float:
    backoff = min(MAX_DELAY, MIN_DELAY * (2**attempts))
    return random.uniform(0, backoff)


def capture_failure(session: Session, job_id: uuid.UUID, err_str: str):
    job = session.scalar(select(OutboxJob).where(OutboxJob.id == job_id))

    if job is None:
        raise ResourceNotFoundError(resource="outbox_job", identifier=str(job_id))

    job.attempts += 1
    job.status = JobStatus.PENDING if job.attempts < MAX_ATTEMPTS else JobStatus.FAILED
    job.available_at = func.now() + timedelta(
        milliseconds=calculate_backoff(job.attempts)
    )
    job.lease_expires_at = None
    job.last_error = err_str

    session.add(job)
    session.commit()


def capture_success(session: Session, job_id: uuid.UUID):
    job = session.scalar(select(OutboxJob).where(OutboxJob.id == job_id))

    if job is None:
        raise ResourceNotFoundError(resource="outbox_job", identifier=str(job_id))

    job.attempts += 1
    job.status = JobStatus.COMPLETED
    job.lease_expires_at = None
    job.completed_at = func.now()

    session.add(job)
    session.execute(delete(CranePhoto).where(CranePhoto.storage_key == job.storage_key))
    session.commit()


def run_delete_batch(session: Session, shutdown: threading.Event) -> int:
    try:
        claimed_jobs = claim_jobs(
            session=session, operation=JobOperation.DELETE, batch_size=JOB_BATCH_SIZE
        )
    except SQLAlchemyError as e:
        logger.warning("delete_batch_failed", extra={"reason": str(e)})
        session.rollback()
        return 0

    processed_jobs = 0
    for job in claimed_jobs:
        if shutdown.is_set():
            return processed_jobs
        processed_jobs += 1
        try:
            storage_service.delete_photo(object_key=job.storage_key)
        except PhotoStorageError as e:
            try:
                capture_failure(session=session, job_id=job.id, err_str=str(e))
            except ResourceNotFoundError:
                # TODO: Consider if need to log delete_crane result too
                logger.warning(
                    "job_status_update_failed",
                    extra={"job_id": str(job.id), "reason": "job_not_found"},
                )
                session.rollback()
            except SQLAlchemyError as sql_err:
                logger.warning(
                    "job_status_update_failed",
                    extra={"job_id": str(job.id), "reason": str(sql_err)},
                )
                session.rollback()
            else:
                logger.warning(
                    "delete_crane_job_failed",
                    extra={"job_id": str(job.id), "reason": str(e)},
                )

        else:
            try:
                capture_success(session=session, job_id=job.id)
            except ResourceNotFoundError:
                logger.warning(
                    "job_status_update_failed",
                    extra={"job_id": str(job.id), "reason": "job_not_found"},
                )
                session.rollback()
            except SQLAlchemyError as sql_err:
                logger.warning(
                    "job_status_update_failed",
                    extra={"job_id": str(job.id), "reason": str(sql_err)},
                )
                session.rollback()
            else:
                logger.info("delete_crane_job_completed", extra={"job_id": str(job.id)})

    return processed_jobs


# find CranePhotos that are pending upload but older than some upload window
# and mark for delete
def run_reap_crane_photos(session: Session) -> int:
    try:
        query = (
            select(CranePhoto)
            .where(
                and_(
                    CranePhoto.status == CranePhotoStatus.PENDING_UPLOAD,
                    CranePhoto.added_at
                    + text(f"INTERVAL '{PENDING_UPLOAD_WINDOW} milliseconds'")
                    < func.now(),
                )
            )
            .order_by(CranePhoto.added_at)
            .limit(JOB_BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )

        photos = session.scalars(query).all()

        for photo in photos:
            photo_service.create_delete_crane_job(session=session, photo=photo)

        session.commit()
        return len(photos)
    except SQLAlchemyError as e:
        logger.warning("reap_crane_photos_failed", extra={"reason": str(e)})
        session.rollback()
        return 0
