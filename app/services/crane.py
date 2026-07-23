import logging
import uuid
from collections.abc import Sequence
from typing import NamedTuple

from geoalchemy2 import WKTElement
from geoalchemy2.functions import ST_MakeEnvelope
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    GeocodeRetrievalError,
    InvalidCoordinateError,
    ResourceNotFoundError,
)
from app.models.base import Crane
from app.schemas.base import CraneCreate
from app.services.geocode import GeocodeData, reverse_geocode

logger = logging.getLogger(__name__)

CRANE_LIST_LIMIT = 5000


class CraneListResult(NamedTuple):
    cranes: Sequence[Crane]
    truncated: bool


def create_crane(session: Session, input: CraneCreate) -> Crane:
    try:
        geocode_data = reverse_geocode(lat=input.lat, lng=input.lng)
    except GeocodeRetrievalError as e:
        logger.warning(
            "reverse_geocode_failed",
            extra={"lat": input.lat, "lng": input.lng, "reason": str(e)},
        )
        geocode_data = GeocodeData(city=None, neighborhood=None)

    crane = Crane(
        **input.model_dump(),
        city=geocode_data.city,
        neighborhood=geocode_data.neighborhood,
        location=WKTElement(f"POINT({input.lng} {input.lat})", srid=4326),
    )

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
    session: Session,
    north: float,
    south: float,
    east: float,
    west: float,
    limit: int = CRANE_LIST_LIMIT,
) -> CraneListResult:
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

    bbox = ST_MakeEnvelope(west, south, east, north, 4326)

    query = (
        select(Crane)
        .where(Crane.location.intersects(bbox))
        .order_by(Crane.added_at.desc())
        .limit(limit + 1)
    )
    rows = session.execute(query).scalars().all()
    truncated = len(rows) > limit

    logger.info(
        "resume_list_get_succeeded",
        extra={"crane_count": str(len(rows)), "truncated": truncated},
    )
    return CraneListResult(cranes=rows[:limit], truncated=truncated)
