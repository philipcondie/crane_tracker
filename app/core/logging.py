import logging
import sys

from asgi_correlation_id.context import correlation_id
from pythonjsonlogger.json import JsonFormatter


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = correlation_id.get() or "-"
        return True


def configure_logging(level: str = "INFO") -> None:
    level = level.upper()

    valid_levels = logging.getLevelNamesMapping()
    if level not in valid_levels:
        raise ValueError(
            f"Invalid log level: {level!r}. Must be one of {list(valid_levels)}"
        )

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level=level)

    handler = logging.StreamHandler(sys.stdout)
    formatter = JsonFormatter(
        "%(asctime)s %(levelname)s %(request_id)s %(name)s "
        "%(funcName)s %(lineno)d %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    )
    handler.setFormatter(formatter)
    handler.addFilter(CorrelationIdFilter())
    root.addHandler(handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("python_multipart").setLevel(logging.WARNING)

    logging.getLogger(__name__).info("logging configured", extra={"log_level": level})
