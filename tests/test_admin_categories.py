import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from backend.apps.admin import auth as admin_auth_module
from backend.config.database import get_pool
from fastapi.testclient import TestClient

CATEGORY_ID = UUID("00000000-0000-0000-0000-000000000001")
PARENT_ID = UUID("00000000-0000-0000-0000-000000000002")
ADMIN_ID = UUID("40000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 1, 1, tzinfo=UTC)


class DummyPool:
    async def close(self) -> None:
        return None


async def create_dummy_pool() -> DummyPool:
    return DummyPool()


def category_record(
    *,
    category_id: UUID = CATEGORY_ID,
    parent_id: UUID | None = None,
    slug: str = "healthy-bowls",
    name: str | None = None,
    description: str | None = None,
    status: str = "active",
    sort_order: int = 10,
) -> dict[str, object]:
    return {
        "id": category_id,
        "parent_id": parent_id,
        "slug": slug,
        "name": name
        or json.dumps(
            {
                "HY-AM": "Healthy Bowls HY",
                "EN-US": "Healthy Bowls",
                "RU-RU": "Healthy Bowls RU",
            }
        ),
        "description": description or json.dumps({"EN-US": "Fresh meals"}),
        "status": status,
        "sort_order": sort_order,
        "created_at": NOW,
        "updated_at": NOW,
    }


class CreateCategoryPool:
    def __init__(self) -> None:
        self.insert_args: tuple[object, ...] | None = None

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "SELECT EXISTS" in query:
            return {"exists": True}

        if "INSERT INTO categories" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        self.insert_args = args
        return category_record(
            parent_id=args[0] if isinstance(args[0], UUID) else None,
            slug=str(args[1]),
            name=str(args[2]),
            description=str(args[3]),
            status=str(args[4]),
            sort_order=int(args[5]),
        )


class ListCategoryPool:
    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "SELECT count(*) AS total" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        assert args == ("active",)
        return {"total": 101}

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        if "FROM categories" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        assert args == ("active", 50, 50)
        return [category_record()]


class DeleteCategoryPool:
    def __init__(self) -> None:
        self.deleted_category_id: UUID | None = None

    async def execute(self, query: str, *args: object) -> str:
        if "DELETE FROM categories" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        self.deleted_category_id = args[0] if isinstance(args[0], UUID) else None
        return "DELETE 1"


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


def test_admin_can_create_category(monkeypatch: Any) -> None:
    pool = CreateCategoryPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/categories",
                json={
                    "parent_id": str(PARENT_ID),
                    "slug": "healthy-bowls",
                    "name": {
                        "HY-AM": "Healthy Bowls HY",
                        "EN-US": "Healthy Bowls",
                        "RU-RU": "Healthy Bowls RU",
                    },
                    "description": {"EN-US": "Fresh meals"},
                    "status": "active",
                    "sort_order": 10,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["name"] == {
        "HY-AM": "Healthy Bowls HY",
        "EN-US": "Healthy Bowls",
        "RU-RU": "Healthy Bowls RU",
    }
    assert response.json()["description"] == {"EN-US": "Fresh meals"}
    assert pool.insert_args is not None
    assert json.loads(str(pool.insert_args[2])) == {
        "HY-AM": "Healthy Bowls HY",
        "EN-US": "Healthy Bowls",
        "RU-RU": "Healthy Bowls RU",
    }


def test_admin_can_list_active_categories(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, ListCategoryPool())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/admin/categories?status=active&page=2&limit=50")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total"] == 101
    assert response.json()["page"] == 2
    assert response.json()["limit"] == 50
    assert response.json()["total_pages"] == 3
    assert "offset" not in response.json()
    assert response.json()["items"][0]["slug"] == "healthy-bowls"


def test_admin_delete_category_returns_no_content(monkeypatch: Any) -> None:
    pool = DeleteCategoryPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.delete(f"/api/v1/admin/categories/{CATEGORY_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert pool.deleted_category_id == CATEGORY_ID
