import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidCoordinateError, ResourceNotFoundError
from app.models.base import Crane
from app.schemas.base import CraneCreate

logger = logging.getLogger(__name__)


def create_crane(session: Session, input: CraneCreate) -> Crane:
    crane = Crane(**input.model_dump())

    session.add(crane)
    session.flush()
    session.refresh(crane)

    logger.info("crane_created", extra={"crane_id": str(crane.id)})
    return crane


def get_crane(session: Session, id: uuid.UUID) -> Crane:
    query = select(Crane).where(Crane.id == id)
    row = session.execute(query)

    crane = row.scalar_one_or_none()
    if crane is None:
        logger.warning(
            "crane_get_failed", extra={"crane_id": str(id), "reason": "crane_not_found"}
        )
        raise ResourceNotFoundError(resource="crane", identifier=str(id))

    logger.info("crane_retrieved", extra={"crane_id": str(id)})
    return crane


def delete_crane(session: Session, id: uuid.UUID) -> None:
    query = select(Crane).where(Crane.id == id)
    row = session.execute(query)
    crane = row.scalar_one_or_none()

    if crane is None:
        logger.warning(
            "crane_delete_failed",
            extra={"crane_id": str(id), "reason": "crane_not_found"},
        )
        raise ResourceNotFoundError(resource="crane", identifier=str(id))

    session.delete(crane)
    session.flush()
    logger.info("crane_deleted", extra={"crane_id": str(id)})


def get_cranes(
    session: Session, north: float, south: float, east: float, west: float
) -> Sequence[Crane]:
    if north > 90 or north < -90 or south > 90 or south < -90:
        logger.warning(
            "crane_list_get_failed",
            extra={
                "reason": "lat out of bounds",
                "north": str(north),
                "south": str(south),
            },
        )
        raise InvalidCoordinateError("Latitude must be between -90 and +90")
    if east > 180 or east < -180 or west > 180 or west < -180:
        logger.warning(
            "crane_list_get_failed",
            extra={"reason": "lng out of bounds", "east": str(east), "west": str(west)},
        )
        raise InvalidCoordinateError("Longitude must be between -180 and +180")

    if north <= south:
        logger.warning(
            "crane_list_get_failed",
            extra={"reason": "invalid lat", "north": str(north), "south": str(south)},
        )
        raise InvalidCoordinateError("North must be > South")
    if east <= west:
        logger.warning(
            "crane_list_get_failed",
            extra={"reason": "invalid lng", "east": str(east), "west": str(west)},
        )
        raise InvalidCoordinateError("East must be > West")

    query = select(Crane).where(
        Crane.lat <= north, Crane.lat >= south, Crane.lng <= east, Crane.lng >= west
    )
    rows = session.execute(query)
    cranes = rows.scalars().all()

    logger.info("resume_list_get_succeeded", extra={"crane_count": str(len(cranes))})
    return cranes
