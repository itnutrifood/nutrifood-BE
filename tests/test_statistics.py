from collections.abc import Mapping, Sequence
from typing import Any

from backend.config.cache import get_cache_client
from backend.config.database import get_pool
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError


class DummyPool:
    async def close(self) -> None:
        return None


async def create_dummy_pool() -> DummyPool:
    return DummyPool()


class StatisticsPool:
    def __init__(self) -> None:
        self.fetch_count = 0

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        assert not args
        assert "SELECT count(*) FROM orders" in query
        assert "SELECT count(*) FROM products" in query
        assert "SELECT round(avg(rating), 1)" in query
        assert "status = 'active'::testimonial_status" in query
        self.fetch_count += 1
        return {
            "happy_customers": 125,
            "healty_meals": 24,
            "customer_rating": 4.8,
        }


class UnexpectedDatabasePool:
    async def fetchrow(self, query: str, *args: object) -> None:
        raise AssertionError(f"Database should not be queried: {query} {args}")


class StatisticsCache:
    def __init__(self, values: Sequence[object | None]) -> None:
        self.values = list(values)
        self.requested_keys: list[str] | None = None
        self.stored_values: dict[str, object] | None = None

    async def mget(self, keys: list[str]) -> list[object | None]:
        self.requested_keys = keys
        return self.values

    async def mset(self, mapping: Mapping[str, object]) -> bool:
        self.stored_values = dict(mapping)
        return True


class UnavailableStatisticsCache:
    async def mget(self, keys: list[str]) -> list[object | None]:
        raise RedisConnectionError(f"Redis unavailable for {keys}")

    async def mset(self, mapping: Mapping[str, object]) -> bool:
        raise RedisConnectionError(f"Redis unavailable for {mapping}")


def configure_test_app(monkeypatch: Any, pool: object, cache: object) -> Any:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_cache_client] = lambda: cache
    return app


def test_statistics_endpoint_returns_complete_cached_values(monkeypatch: Any) -> None:
    cache = StatisticsCache(["125", "24", "4.8"])
    app = configure_test_app(monkeypatch, UnexpectedDatabasePool(), cache)

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/statistics")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "happy_customers": 125,
        "healty_meals": 24,
        "customer_rating": 4.8,
    }
    assert cache.stored_values is None


def test_statistics_endpoint_recomputes_and_caches_when_any_key_is_missing(
    monkeypatch: Any,
) -> None:
    pool = StatisticsPool()
    cache = StatisticsCache(["120", None, "4.7"])
    app = configure_test_app(monkeypatch, pool, cache)

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/statistics")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "happy_customers": 125,
        "healty_meals": 24,
        "customer_rating": 4.8,
    }
    assert pool.fetch_count == 1
    assert cache.stored_values == {
        "nutrifood:statistics:happy_customers": "125",
        "nutrifood:statistics:healty_meals": "24",
        "nutrifood:statistics:customer_rating": "4.8",
    }


def test_statistics_endpoint_uses_database_when_redis_is_unavailable(
    monkeypatch: Any,
) -> None:
    pool = StatisticsPool()
    app = configure_test_app(monkeypatch, pool, UnavailableStatisticsCache())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/statistics")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["happy_customers"] == 125
    assert pool.fetch_count == 1
