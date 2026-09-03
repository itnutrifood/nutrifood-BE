import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg
from backend.apps.admin import auth as admin_auth_module
from backend.config.database import get_pool
from fastapi.testclient import TestClient

INGREDIENT_ID = UUID("70000000-0000-0000-0000-000000000001")
ADMIN_ID = UUID("40000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 1, 1, tzinfo=UTC)


class DummyPool:
    async def close(self) -> None:
        return None


async def create_dummy_pool() -> DummyPool:
    return DummyPool()


def localized_name(en_us: str = "Broccoli") -> dict[str, str]:
    return {
        "HY-AM": "Բրոկկոլի",
        "EN-US": en_us,
        "RU-RU": "Брокколи",
    }


def ingredient_record(
    *,
    ingredient_id: UUID = INGREDIENT_ID,
    name: str | None = None,
) -> dict[str, object]:
    return {
        "id": ingredient_id,
        "name": name or json.dumps(localized_name()),
        "created_at": NOW,
        "updated_at": NOW,
    }


def configure_test_app(monkeypatch: Any, pool: object) -> Any:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    app.dependency_overrides[admin_auth_module.admin_auth] = lambda: admin_auth_module.AdminUser(
        id=ADMIN_ID,
        username="admin@mail.com",
        token_version=1,
    )
    app.dependency_overrides[get_pool] = lambda: pool
    return app


class CreateIngredientPool:
    def __init__(self) -> None:
        self.insert_args: tuple[object, ...] | None = None

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "INSERT INTO ingredients" in query
        self.insert_args = args
        return ingredient_record(name=str(args[0]))


class ListIngredientsPool:
    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert query == "SELECT count(*) AS total FROM ingredients"
        assert args == ()
        return {"total": 26}

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert "ORDER BY lower(name ->> 'EN-US'), id" in query
        assert args == (25, 25)
        return [ingredient_record()]


class ReadIngredientPool:
    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "FROM ingredients WHERE id = $1" in query
        assert args == (INGREDIENT_ID,)
        return ingredient_record()


class UpdateIngredientPool:
    def __init__(self) -> None:
        self.update_args: tuple[object, ...] | None = None

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "UPDATE ingredients" in query
        self.update_args = args
        return ingredient_record(name=str(args[0]))


class DeleteIngredientPool:
    def __init__(self) -> None:
        self.deleted_ingredient_id: UUID | None = None

    async def execute(self, query: str, *args: object) -> str:
        assert query == "DELETE FROM ingredients WHERE id = $1"
        self.deleted_ingredient_id = args[0] if isinstance(args[0], UUID) else None
        return "DELETE 1"


class MissingIngredientPool:
    async def fetchrow(self, query: str, *args: object) -> None:
        assert "FROM ingredients WHERE id = $1" in query
        assert args == (INGREDIENT_ID,)
        return None


class DuplicateIngredientPool:
    async def fetchrow(self, query: str, *args: object) -> None:
        assert "INSERT INTO ingredients" in query
        raise asyncpg.UniqueViolationError


def test_admin_can_create_localized_ingredient(monkeypatch: Any) -> None:
    pool = CreateIngredientPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/ingredients",
                json={"name": localized_name()},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["name"] == localized_name()
    assert pool.insert_args is not None
    assert json.loads(str(pool.insert_args[0])) == localized_name()


def test_admin_can_list_ingredients(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, ListIngredientsPool())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/admin/ingredients?page=2&limit=25")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total"] == 26
    assert response.json()["page"] == 2
    assert response.json()["total_pages"] == 2
    assert response.json()["items"][0]["name"] == localized_name()


def test_admin_can_read_ingredient(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, ReadIngredientPool())

    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/admin/ingredients/{INGREDIENT_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["id"] == str(INGREDIENT_ID)


def test_admin_can_update_all_ingredient_translations(monkeypatch: Any) -> None:
    pool = UpdateIngredientPool()
    app = configure_test_app(monkeypatch, pool)
    updated_name = localized_name("Tenderstem broccoli")

    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/admin/ingredients/{INGREDIENT_ID}",
                json={"name": updated_name},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["name"] == updated_name
    assert pool.update_args is not None
    assert json.loads(str(pool.update_args[0])) == updated_name
    assert pool.update_args[1] == INGREDIENT_ID


def test_admin_can_delete_ingredient(monkeypatch: Any) -> None:
    pool = DeleteIngredientPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.delete(f"/api/v1/admin/ingredients/{INGREDIENT_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert pool.deleted_ingredient_id == INGREDIENT_ID


def test_admin_ingredient_requires_all_three_languages(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, object())

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/ingredients",
                json={"name": {"EN-US": "Broccoli", "RU-RU": "Брокколи"}},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_admin_cannot_create_duplicate_ingredient(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, DuplicateIngredientPool())

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/ingredients",
                json={"name": localized_name()},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"] == "Ingredient already exists"


def test_admin_ingredient_patch_rejects_empty_payload(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, object())

    try:
        with TestClient(app) as client:
            response = client.patch(f"/api/v1/admin/ingredients/{INGREDIENT_ID}", json={})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_missing_ingredient_returns_not_found(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, MissingIngredientPool())

    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/admin/ingredients/{INGREDIENT_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "Ingredient not found"
