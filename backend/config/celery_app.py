from celery import Celery
from celery.signals import setup_logging, worker_process_init

from backend.config.celery_schedule import beat_schedule
from backend.config.logging import configure_logging
from backend.config.settings import get_settings

settings = get_settings()


def _configure_celery_logging(**_kwargs: object) -> None:
    configure_logging(settings)


def _configure_worker_process_logging(**_kwargs: object) -> None:
    configure_logging(settings)


setup_logging.connect(_configure_celery_logging)
worker_process_init.connect(_configure_worker_process_logging)

app = Celery(
    "nutrifood",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=(
        "backend.apps.notifications.tasks",
        "backend.apps.statistics.tasks",
    ),
)
app.conf.update(
    accept_content=("json",),
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3_600},
    enable_utc=True,
    result_backend_transport_options={
        "global_keyprefix": "nutrifood:result:",
        "retry_policy": {"timeout": 5.0},
    },
    result_expires=settings.celery_result_expires_seconds,
    result_serializer="json",
    task_default_queue="default",
    task_ignore_result=True,
    task_routes={
        "backend.apps.notifications.tasks.*": {"queue": "periodic"},
        "backend.apps.statistics.tasks.*": {"queue": "periodic"},
    },
    task_serializer="json",
    task_store_errors_even_if_ignored=True,
    timezone=settings.celery_timezone,
    worker_concurrency=settings.celery_worker_concurrency,
    worker_prefetch_multiplier=1,
    beat_schedule=beat_schedule,
)
