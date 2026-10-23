import logging
import signal
import threading

from app.core.config import get_settings
from app.core.database import session_scope
from app.core.logging import configure_logging
from app.worker.photo_jobs import run_delete_batch, run_reap_crane_photos

settings = get_settings()
log_level = (
    "DEBUG" if settings.environment.lower() in ("dev", "development") else "INFO"
)
configure_logging(level=log_level)
logger = logging.getLogger(__name__)

shutdown = threading.Event()


def _handle_shutdown(signum, frame):
    shutdown.set()


signal.signal(signal.SIGTERM, _handle_shutdown)
signal.signal(signal.SIGINT, _handle_shutdown)

WORKER_SLEEP_PERIOD = settings.worker_sleep_period

while not shutdown.is_set():
    processed = 0
    try:
        with session_scope("worker") as session:
            processed += run_delete_batch(session=session, shutdown=shutdown)
            processed += run_reap_crane_photos(session=session)
    except Exception:
        logger.exception("worker_cycle_failed", extra={"operation": "worker_main"})

    if processed == 0:
        shutdown.wait(WORKER_SLEEP_PERIOD)

logger.info("worker_shutdown_completed", extra={"operation": "worker_main"})
