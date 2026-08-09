import logging
import random
import uuid
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import app.services.storage as storage_service
from app.core.config import get_settings
from app.core.exceptions import PhotoStorageError, ResourceNotFoundError
from app.models.base import CranePhoto, JobOperation, JobStatus, OutboxJob
from app.worker.claim import claim_jobs

settings = get_settings()
logger = logging.getLogger(__name__)

JOB_BATCH_SIZE = settings.job_batch_size
MAX_ATTEMPTS = 5
MIN_DELAY = 100  # ms
MAX_DELAY = 4000  # ms


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


def run_delete_batch(session: Session):
    try:
        claimed_jobs = claim_jobs(
            session=session, operation=JobOperation.DELETE, batch_size=JOB_BATCH_SIZE
        )
    except SQLAlchemyError:
        logger.warning("delete_batch_failed", extra={"reason": "failed_to_claim_batch"})
        return

    for job in claimed_jobs:
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
            except SQLAlchemyError as sql_err:
                logger.warning(
                    "job_status_update_failed",
                    extra={"job_id": str(job.id), "reason": str(sql_err)},
                )
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
            except SQLAlchemyError as sql_err:
                logger.warning(
                    "job_status_update_failed",
                    extra={"job_id": str(job.id), "reason": str(sql_err)},
                )
            else:
                logger.info("delete_crane_job_completed", extra={"job_id": str(job.id)})
