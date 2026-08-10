from sqlalchemy.orm import Session

from app.models.base import JobOperation, OutboxJob


def create_task(session: Session, *, operation: JobOperation, storage_key: str):
    job = OutboxJob(operation=operation, storage_key=storage_key)

    session.add(job)
    session.flush()


def update_task():
    pass
