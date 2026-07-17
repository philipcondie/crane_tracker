import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidCoordinateError, ResourceNotFoundError
from app.models.base import Crane
from app.schemas.base import CraneCreate


def create_crane(session: Session, input: CraneCreate) -> Crane:
    crane = Crane(**input.model_dump())

    session.add(crane)
    session.flush()
    session.refresh(crane)

    return crane


def get_crane(session: Session, id: uuid.UUID) -> Crane:
    query = select(Crane).where(Crane.id == id)
    row = session.execute(query)

    crane = row.scalar_one_or_none()
    if crane is None:
        # add logging here
        raise ResourceNotFoundError(resource="crane", identifier=str(id))

    return crane


def delete_crane(session: Session, id: uuid.UUID) -> None:
    query = select(Crane).where(Crane.id == id)
    row = session.execute(query)
    crane = row.scalar_one_or_none()

    if crane is None:
        # add logging here
        raise ResourceNotFoundError(resource="crane", identifier=str(id))

    session.delete(crane)
    session.flush()


def get_cranes(
    session: Session, north: float, south: float, east: float, west: float
) -> Sequence[Crane]:
    if north > 90 or north < -90 or south > 90 or south < -90:
        raise InvalidCoordinateError("Latitude must be between -90 and +90")
    if east > 180 or east < -180 or west > 180 or west < -180:
        raise InvalidCoordinateError("Longitude must be between -180 and +180")

    if north <= south:
        raise InvalidCoordinateError("North and South must have different values")
    if east <= west:
        raise InvalidCoordinateError("East and West must have different values")

    query = select(Crane).where(
        Crane.lat <= north, Crane.lat >= south, Crane.lng <= east, Crane.lng >= west
    )
    rows = session.execute(query)
    cranes = rows.scalars().all()

    return cranes
