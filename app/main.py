from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.exception_handlers import (
    duplicate_crane_error_handler,
    duplicate_gone_report_error_handler,
    invalid_photo_error_handler,
    photo_limit_exceeded_error_handler,
    resource_not_found_error_handler,
    sql_alchemy_error_handler,
)
from app.core.exceptions import (
    DuplicateCraneError,
    DuplicateGoneReportError,
    InvalidPhotoError,
    PhotoLimitExceededError,
    ResourceNotFoundError,
)
from app.core.limiter import limiter
from app.core.logging import configure_logging
from app.routes.crane import crane_router
from app.routes.health import health_router

settings = get_settings()
log_level = (
    "DEBUG" if settings.environment.lower() in ("dev", "development") else "INFO"
)
configure_logging(level=log_level)

origins = settings.cors_origins
methods = (
    ["*"] if settings.environment.lower() == "dev" else ["GET", "PUT", "POST", "DELETE"]
)

app = FastAPI()
app.state.limiter = limiter

app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=methods,
    allow_headers=["*"],
)

app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,  # pyright: ignore[reportArgumentType]
)
app.add_exception_handler(
    DuplicateCraneError,
    duplicate_crane_error_handler,  # pyright: ignore[reportArgumentType]
)
app.add_exception_handler(
    ResourceNotFoundError,
    resource_not_found_error_handler,  # pyright: ignore[reportArgumentType]
)
app.add_exception_handler(
    DuplicateGoneReportError,
    duplicate_gone_report_error_handler,  # pyright: ignore[reportArgumentType]
)
app.add_exception_handler(
    InvalidPhotoError,
    invalid_photo_error_handler,  # pyright: ignore[reportArgumentType]
)
app.add_exception_handler(
    PhotoLimitExceededError,
    photo_limit_exceeded_error_handler,  # pyright: ignore[reportArgumentType]
)
app.add_exception_handler(
    SQLAlchemyError,
    sql_alchemy_error_handler,  # pyright: ignore[reportArgumentType]
)

app.include_router(crane_router)
app.include_router(health_router)
