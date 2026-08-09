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
    with session_scope("worker") as session:
        delete_batch_size = run_delete_batch(session=session, shutdown=shutdown)
        logger.info("run_delete_batch_completed")
        reap_batch_size = run_reap_crane_photos(session=session)
        logger.info("run_reap_crane_photos_completed")
    if delete_batch_size + reap_batch_size == 0:
        shutdown.wait(WORKER_SLEEP_PERIOD)

logger.info("Shutting down")
