import logging

from fastapi import APIRouter

health_router = APIRouter(prefix="/health", tags=["health"])

logger = logging.getLogger(__name__)


@health_router.get("")
def healthcheck():
    logger.info("health checked", extra={"status": "ok"})
    return {"status": "ok"}
