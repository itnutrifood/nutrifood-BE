import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from concurrent_log_handler import ConcurrentTimedRotatingFileHandler

from backend.config.settings import Settings, get_settings

LOG_FORMAT = "%(asctime)s %(levelname)s pid=%(process)d %(name)s %(message)s"
MANAGED_HANDLER_NAMES = frozenset({"nutrifood-console", "nutrifood-file"})
FRAMEWORK_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "celery",
    "celery.task",
)
SENSITIVE_HTTP_LOGGERS = ("httpx", "httpcore")
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class UTCFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=UTC)
        if datefmt is not None:
            return timestamp.strftime(datefmt)
        return timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def log_file_path(settings: Settings) -> Path:
    return settings.log_directory / f"{settings.log_component}.log"


def create_daily_file_handler(settings: Settings) -> ConcurrentTimedRotatingFileHandler:
    handler = ConcurrentTimedRotatingFileHandler(
        filename=str(log_file_path(settings).resolve()),
        when="midnight",
        interval=1,
        backupCount=settings.log_retention_days,
        encoding="utf-8",
        delay=True,
        utc=settings.log_rotation_utc,
        use_gzip=True,
        chmod=0o640,
    )
    handler.set_name("nutrifood-file")
    return handler


def _remove_managed_handlers(logger: logging.Logger) -> None:
    for handler in tuple(logger.handlers):
        if handler.get_name() not in MANAGED_HANDLER_NAMES:
            continue
        logger.removeHandler(handler)
        handler.close()


def configure_logging(settings: Settings | None = None) -> None:
    resolved_settings = settings or get_settings()
    resolved_settings.log_directory.mkdir(parents=True, exist_ok=True)

    level = LOG_LEVELS[resolved_settings.log_level]
    formatter = UTCFormatter(LOG_FORMAT)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.set_name("nutrifood-console")
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    file_handler = create_daily_file_handler(resolved_settings)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    _remove_managed_handlers(root_logger)
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    for logger_name in FRAMEWORK_LOGGERS:
        framework_logger = logging.getLogger(logger_name)
        for handler in tuple(framework_logger.handlers):
            framework_logger.removeHandler(handler)
            handler.close()
        framework_logger.setLevel(level)
        framework_logger.propagate = True

    # HTTPX logs complete request URLs at INFO. The Yandex Geocoder key is a query
    # parameter, so keep these transport logs below WARNING even in debug mode.
    for logger_name in SENSITIVE_HTTP_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    logging.captureWarnings(True)
