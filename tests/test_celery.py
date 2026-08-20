from typing import Any

import pytest
from backend.apps.notifications import tasks
from backend.apps.statistics import tasks as statistics_tasks
from backend.apps.statistics.schemas import PublicStatistics
from backend.config.celery_app import app
from backend.config.settings import Settings

TASK_NAME = "backend.apps.notifications.tasks.prune_stale_fcm_registrations"
STATISTICS_TASK_NAME = "backend.apps.statistics.tasks.refresh_statistics_cache"


class TaskPool:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class TaskCache:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


def test_celery_uses_json_and_short_lived_redis_results() -> None:
    assert app.conf.task_serializer == "json"
    assert app.conf.result_serializer == "json"
    assert app.conf.accept_content == ("json",)
    assert app.conf.task_ignore_result is True
    assert app.conf.task_store_errors_even_if_ignored is True
    assert app.conf.result_expires == 604_800
    assert app.conf.worker_prefetch_multiplier == 1


def test_periodic_cleanup_is_registered_on_the_periodic_queue() -> None:
    schedule: dict[str, Any] = app.conf.beat_schedule["prune-stale-fcm-registrations"]

    assert schedule["task"] == TASK_NAME
    assert schedule["options"] == {"queue": "periodic", "expires": 21_600}

    task = app.tasks[TASK_NAME]
    assert task.acks_late is True
    assert task.ignore_result is True
    assert task.max_retries == 3


def test_daily_statistics_refresh_is_registered_on_the_periodic_queue() -> None:
    schedule: dict[str, Any] = app.conf.beat_schedule["refresh-public-statistics-cache"]

    assert schedule["task"] == STATISTICS_TASK_NAME
    assert schedule["schedule"].minute == {0}
    assert schedule["schedule"].hour == {0}
    assert schedule["options"] == {"queue": "periodic", "expires": 21_600}

    task = app.tasks[STATISTICS_TASK_NAME]
    assert task.acks_late is True
    assert task.ignore_result is True
    assert task.max_retries == 3


async def test_cleanup_task_owns_and_closes_its_database_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = TaskPool()
    received: tuple[object, int] | None = None

    async def create_task_pool() -> TaskPool:
        return pool

    async def prune_service(task_pool: object, *, stale_days: int) -> int:
        nonlocal received
        received = (task_pool, stale_days)
        return 5

    monkeypatch.setattr(tasks, "create_pool", create_task_pool)
    monkeypatch.setattr(tasks, "prune_service", prune_service)
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: Settings(_env_file=None, fcm_registration_stale_days=45),
    )

    removed_count = await tasks._prune_stale_fcm_registrations()

    assert removed_count == 5
    assert received == (pool, 45)
    assert pool.closed is True


async def test_statistics_task_owns_and_closes_database_and_cache_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = TaskPool()
    cache = TaskCache()
    received: tuple[object, object] | None = None

    async def create_task_pool() -> TaskPool:
        return pool

    async def refresh_service(task_pool: object, task_cache: object) -> PublicStatistics:
        nonlocal received
        received = (task_pool, task_cache)
        return PublicStatistics(happy_customers=8, healty_meals=3, customer_rating=4.5)

    monkeypatch.setattr(statistics_tasks, "create_pool", create_task_pool)
    monkeypatch.setattr(statistics_tasks, "create_cache_client", lambda: cache)
    monkeypatch.setattr(statistics_tasks, "refresh_service", refresh_service)

    statistics = await statistics_tasks._refresh_statistics_cache()

    assert statistics.happy_customers == 8
    assert received == (pool, cache)
    assert cache.closed is True
    assert pool.closed is True
