from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.routes.crane import crane_router

settings = get_settings()
log_level = "DEBUG" if settings.environment.lower() == "dev" else "INFO"
configure_logging(level=log_level)

app = FastAPI()

app.add_middleware(CorrelationIdMiddleware)

app.include_router(crane_router)
