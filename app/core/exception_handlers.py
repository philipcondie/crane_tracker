import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

import app.core.exceptions as exceptions

logger = logging.getLogger(__name__)


def duplicate_crane_error_handler(
    request: Request, exc: exceptions.DuplicateCraneError
):
    logger.warning(
        "duplicate_crane",
        extra={
            "operation": request.scope["route"].name,
            "path": request.url.path,
            "lat": exc.lat,
            "lng": exc.lng,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)}
    )


def invalid_photo_error_handler(request: Request, exc: exceptions.InvalidPhotoError):
    logger.warning(
        "invalid_photo",
        extra={
            "operation": request.scope["route"].name,
            "path": request.url.path,
            "error": type(exc).__name__,
        },
    )
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


def photo_limit_exceeded_error_handler(
    request: Request, exc: exceptions.PhotoLimitExceededError
):
    logger.warning(
        "photo_limit_exceeded",
        extra={
            "operation": request.scope["route"].name,
            "path": request.url.path,
            "crane_id": str(exc.crane_id),
            "active_photo_count": exc.active_photo_count,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)}
    )


def resource_not_found_error_handler(
    request: Request, exc: exceptions.ResourceNotFoundError
):
    logger.warning(
        "resource_not_found",
        extra={
            "operation": request.scope["route"].name,
            "path": request.url.path,
            "resource": exc.resource,
            "id": exc.identifier,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)}
    )


def duplicate_gone_report_error_handler(
    request: Request, exc: exceptions.DuplicateGoneReportError
):
    logger.warning(
        "duplicate_gone_report",
        extra={
            "operation": request.scope["route"].name,
            "path": request.url.path,
            "crane_id": str(exc.crane_id),
        },
    )
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)}
    )


def sql_alchemy_error_handler(request: Request, exc: SQLAlchemyError):
    route = request.scope.get("route")
    if route is None:
        route_name = "unknown"
    else:
        route_name = route.name
    logger.exception(
        "database_error",
        extra={
            "operation": route_name,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal Server Error"},
    )
