import uuid

from fastapi import APIRouter, HTTPException, Query, Request, status

import app.services.crane as crane_service
from app.core.dependencies import SessionDep
from app.core.exceptions import (
    DuplicateGoneReportError,
    InvalidCoordinateError,
    ResourceNotFoundError,
)
from app.schemas.base import CraneCreate, CraneDetail, CraneListResponse, CraneSummary

crane_router = APIRouter(prefix="/cranes")


@crane_router.post("", response_model=CraneSummary, status_code=status.HTTP_201_CREATED)
def create_crane(session: SessionDep, crane_input: CraneCreate):
    crane = crane_service.create_crane(session=session, input=crane_input)
    session.commit()
    return crane


@crane_router.get("/{crane_id}", response_model=CraneDetail)
def get_crane(session: SessionDep, crane_id: uuid.UUID):
    try:
        crane = crane_service.get_crane(session=session, id=crane_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return crane


@crane_router.get("", response_model=CraneListResponse)
def get_cranes(
    session: SessionDep,
    north: float = Query(ge=-90, le=90),
    south: float = Query(ge=-90, le=90),
    east: float = Query(ge=-180, le=180),
    west: float = Query(ge=-180, le=180),
):
    try:
        cranes = crane_service.get_cranes(
            session=session, north=north, south=south, east=east, west=west
        )
    except InvalidCoordinateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return cranes


@crane_router.post("/{crane_id}/report")
def report_crane_as_gone(session: SessionDep, crane_id: uuid.UUID, request: Request):
    x_forwarded_for = request.headers.get("X-Forwarded-For")

    if x_forwarded_for:
        client_ip = x_forwarded_for.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else None

    if client_ip is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="could not identify host to record report",
        )

    try:
        crane_service.report_crane_as_gone(
            session=session, crane_id=crane_id, client_ip=client_ip
        )
        session.commit()
    except ResourceNotFoundError as e:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DuplicateGoneReportError as e:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
