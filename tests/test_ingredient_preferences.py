import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from backend.apps.accounts.auth import UserIdentity, get_current_user
from backend.config.database import get_pool
from fastapi.testclient import TestClient

USER_ID = UUID("50000000-0000-0000-0000-000000000001")
BROCCOLI_ID = UUID("70000000-0000-0000-0000-000000000001")
PEANUT_ID = UUID("70000000-0000-0000-0000-000000000002")
MISSING_ID = UUID("70000000-0000-0000-0000-000000000003")
NOW = datetime(2026, 1, 1, tzinfo=UTC)


class DummyPool:
    async def close(self) -> None:
        return None


async def create_dummy_pool() -> DummyPool:
    return DummyPool()


def current_user() -> UserIdentity:
    return UserIdentity(
        id=USER_ID,
        firebase_uid="firebase-user-uid",
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        registration_provider="password",
        sign_in_provider="password",
        roles=frozenset(),
        created_at=NOW,
        updated_at=NOW,
    )


def ingredient_record(ingredient_id: UUID, en_us_name: str) -> dict[str, object]:
    return {
        "id": ingredient_id,
        "name": json.dumps(
            {
                "HY-AM": f"{en_us_name} HY",
                "EN-US": en_us_name,
                "RU-RU": f"{en_us_name} RU",
            }
        ),
        "created_at": NOW,
        "updated_at": NOW,
    }


def configure_test_app(monkeypatch: Any, pool: object, *, authenticated: bool = True) -> Any:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    app.dependency_overrides[get_pool] = lambda: pool
    if authenticated:
        app.dependency_overrides[get_current_user] = current_user
    return app


class PublicIngredientPool:
    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert "FROM ingredients" in query
        assert "ORDER BY lower(name ->> $1), id" in query
        assert args == ("EN-US",)
        return [
            ingredient_record(BROCCOLI_ID, "Broccoli"),
            ingredient_record(PEANUT_ID, "Peanut"),
        ]


class IngredientPreferenceReadPool:
    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert "FROM user_ingredient_preferences" in query
        assert "ORDER BY preference, ingredient_id" in query
        assert args == (USER_ID,)
        return [
            {"ingredient_id": BROCCOLI_ID, "preference": "whitelisted"},
            {"ingredient_id": PEANUT_ID, "preference": "blacklisted"},
        ]


class AsyncContext:
    def __init__(self, value: object) -> None:
        self.value = value

    async def __aenter__(self) -> object:
        return self.value

    async def __aexit__(self, *args: object) -> None:
        return None


class IngredientPreferenceWritePool:
    def __init__(self, *, missing_ids: list[UUID] | None = None) -> None:
        self.missing_ids = set(missing_ids or [])
        self.executions: list[tuple[str, tuple[object, ...]]] = []
        self.user_locked = False

    def acquire(self) -> AsyncContext:
        return AsyncContext(self)

    def transaction(self) -> AsyncContext:
        return AsyncContext(self)

    async def fetchval(self, query: str, *args: object) -> UUID:
        assert query == "SELECT id FROM users WHERE id = $1 FOR UPDATE"
        assert args == (USER_ID,)
        self.user_locked = True
        return USER_ID

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert "FROM ingredients" in query
        assert "FOR KEY SHARE" in query
        assert self.user_locked
        requested_ids = args[0]
        assert isinstance(requested_ids, list)
        return [
            {"id": ingredient_id}
            for ingredient_id in requested_ids
            if ingredient_id not in self.missing_ids
        ]

    async def execute(self, query: str, *args: object) -> str:
        assert self.user_locked
        self.executions.append((query, args))
        return "OK"


def test_users_can_list_all_localized_ingredients(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, PublicIngredientPool())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/en-us/ingredients")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == [
        {"id": str(BROCCOLI_ID), "name": "Broccoli"},
        {"id": str(PEANUT_ID), "name": "Peanut"},
    ]


def test_user_can_read_ingredient_preferences(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, IngredientPreferenceReadPool())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/users/ingredient-preferences")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "whitelisted_ingredient_ids": [str(BROCCOLI_ID)],
        "blacklisted_ingredient_ids": [str(PEANUT_ID)],
    }


def test_put_replaces_ingredient_preferences_atomically(monkeypatch: Any) -> None:
    pool = IngredientPreferenceWritePool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/users/ingredient-preferences",
                json={
                    "whitelisted_ingredient_ids": [str(PEANUT_ID), str(BROCCOLI_ID)],
                    "blacklisted_ingredient_ids": [],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "whitelisted_ingredient_ids": [str(BROCCOLI_ID), str(PEANUT_ID)],
        "blacklisted_ingredient_ids": [],
    }
    assert len(pool.executions) == 2
    delete_query, delete_args = pool.executions[0]
    assert "DELETE FROM user_ingredient_preferences" in delete_query
    assert delete_args == (USER_ID, [BROCCOLI_ID, PEANUT_ID])
    insert_query, insert_args = pool.executions[1]
    assert "ON CONFLICT (user_id, ingredient_id) DO UPDATE" in insert_query
    assert insert_args == (USER_ID, [PEANUT_ID, BROCCOLI_ID], [])


def test_put_rejects_ingredient_in_both_lists(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, object())

    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/users/ingredient-preferences",
                json={
                    "whitelisted_ingredient_ids": [str(BROCCOLI_ID)],
                    "blacklisted_ingredient_ids": [str(BROCCOLI_ID)],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "cannot be both whitelisted and blacklisted" in response.text


def test_put_rejects_duplicate_ingredient_ids(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, object())

    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/users/ingredient-preferences",
                json={
                    "whitelisted_ingredient_ids": [str(BROCCOLI_ID), str(BROCCOLI_ID)],
                    "blacklisted_ingredient_ids": [],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "cannot contain duplicates" in response.text


def test_put_reports_missing_ingredients_without_writing(monkeypatch: Any) -> None:
    pool = IngredientPreferenceWritePool(missing_ids=[MISSING_ID])
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/users/ingredient-preferences",
                json={
                    "whitelisted_ingredient_ids": [str(BROCCOLI_ID)],
                    "blacklisted_ingredient_ids": [str(MISSING_ID)],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "message": "One or more ingredients were not found",
            "ingredient_ids": [str(MISSING_ID)],
        }
    }
    assert pool.executions == []


def test_ingredient_preferences_require_authentication(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, IngredientPreferenceReadPool(), authenticated=False)

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/users/ingredient-preferences")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
