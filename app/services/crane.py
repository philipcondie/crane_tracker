import hashlib
import hmac
import logging
import uuid
from collections.abc import Sequence
from typing import NamedTuple

from geoalchemy2 import Geography, WKTElement
from geoalchemy2.functions import ST_DWithin, ST_MakeEnvelope
from sqlalchemy import cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    DuplicateCraneError,
    DuplicateGoneReportError,
    GeocodeRetrievalError,
    InvalidCoordinateError,
    ResourceNotFoundError,
)
from app.models.base import Crane, GoneReport
from app.schemas.base import CraneInput, CraneStatus
from app.services.geocode import GeocodeData, reverse_geocode

logger = logging.getLogger(__name__)

settings = get_settings()

CRANE_LIST_LIMIT = 5000
CRANE_DUPLICATE_DISTANCE_METERS = 100


def hash_ip(ip_address: str) -> str:
    secret_key = settings.ip_hash_salt.encode()
    return hmac.new(secret_key, ip_address.encode(), hashlib.sha256).hexdigest()


class CraneListResult(NamedTuple):
    cranes: Sequence[Crane]
    truncated: bool


def create_crane(
    session: Session, input: CraneInput, override_duplicate_warning: bool
) -> Crane:
    # look up cranes within radius
    input_point = WKTElement(f"POINT({input.lng} {input.lat})", srid=4326)
    if override_duplicate_warning is False:
        query = (
            select(Crane)
            .where(
                ST_DWithin(
                    cast(Crane.location, Geography),
                    cast(input_point, Geography),
                    CRANE_DUPLICATE_DISTANCE_METERS,
                )
            )
            .exists()
        )
        possible_duplicate = session.scalar(select(query))
        if possible_duplicate:
            logger.info(
                "create_crane_failed",
                extra={
                    "reason": "possible duplicate entry",
                    "lat": input.lat,
                    "lng": input.lng,
                },
            )
            raise DuplicateCraneError()

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
        status=CraneStatus.ACTIVE,
        city=geocode_data.city,
        neighborhood=geocode_data.neighborhood,
        location=input_point,
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
        "crane_list_get_succeeded",
        extra={"crane_count": str(len(rows)), "truncated": truncated},
    )
    return CraneListResult(cranes=rows[:limit], truncated=truncated)


def report_crane_as_gone(
    session: Session,
    crane_id: uuid.UUID,
    client_ip: str,
    threshold: int | None = None,
) -> None:
    if threshold is None:
        threshold = get_settings().gone_report_threshold

    # verify crane exists
    query = select(Crane).where(Crane.id == crane_id).with_for_update()
    row = session.execute(query)
    crane = row.scalar_one_or_none()

    if crane is None:
        logger.warning(
            "gone_report_create_failed",
            extra={"crane_id": str(crane_id), "reason": "crane_not_found"},
        )
        raise ResourceNotFoundError(resource="crane", identifier=str(crane_id))

    # add gone report
    report = GoneReport(crane_id=crane_id, reporter_ip_hash=hash_ip(client_ip))
    try:
        with session.begin_nested():
            session.add(report)
            session.flush()
    except IntegrityError as e:
        logger.warning(
            "gone_report_create_failed",
            extra={"crane_id": str(crane_id), "reason": "duplicate reporter ip"},
        )
        raise DuplicateGoneReportError() from e

    # check gone report count and update status
    query = select(func.count(GoneReport.id)).where(GoneReport.crane_id == crane_id)
    gone_report_count = session.scalar(query)

    logger.info(
        "gone_report_created",
        extra={"crane_id": str(crane_id), "report_count": gone_report_count},
    )

    if gone_report_count and gone_report_count >= threshold:
        crane.status = "gone"

        session.add(crane)
        session.flush()
        session.refresh(crane)
        logger.info(
            "crane_status_updated", extra={"crane_id": str(crane_id), "status": "gone"}
        )
