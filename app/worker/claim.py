import uuid
from dataclasses import dataclass

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from app.models.base import JobOperation, JobStatus, OutboxJob

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
