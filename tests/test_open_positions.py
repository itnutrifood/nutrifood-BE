import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from backend.apps.admin import auth as admin_auth_module
from backend.apps.common.pagination import decode_cursor
from backend.config.database import get_pool
from fastapi.testclient import TestClient

OPEN_POSITION_ID = UUID("60000000-0000-0000-0000-000000000001")
NEXT_OPEN_POSITION_ID = UUID("60000000-0000-0000-0000-000000000002")
ADMIN_ID = UUID("40000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 1, 1, tzinfo=UTC)


class DummyPool:
    async def close(self) -> None:
        return None


async def create_dummy_pool() -> DummyPool:
    return DummyPool()


def localized_text(en_us: str) -> dict[str, str]:
    return {
        "HY-AM": f"{en_us} HY",
        "EN-US": en_us,
        "RU-RU": f"{en_us} RU",
    }


def open_position_record(
    *,
    open_position_id: UUID = OPEN_POSITION_ID,
    employment_type: str = "full_time",
    status: str = "active",
    created_at: datetime = NOW,
) -> dict[str, object]:
    return {
        "id": open_position_id,
        "title": json.dumps(localized_text("Delivery Driver")),
        "employment_type": employment_type,
        "description": json.dumps(localized_text("Deliver healthy meals.")),
        "position": json.dumps(localized_text("Delivery")),
        "city": json.dumps(localized_text("Yerevan")),
        "status": status,
        "created_at": created_at,
        "updated_at": NOW,
    }


def open_position_payload() -> dict[str, object]:
    return {
        "title": localized_text("Delivery Driver"),
        "employment_type": "full_time",
        "description": localized_text("Deliver healthy meals."),
        "position": localized_text("Delivery"),
        "city": localized_text("Yerevan"),
    }


def configure_test_app(monkeypatch: Any, pool: object, *, admin: bool = False) -> Any:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    if admin:
        app.dependency_overrides[admin_auth_module.admin_auth] = lambda: (
            admin_auth_module.AdminUser(
                id=ADMIN_ID,
                username="admin@mail.com",
                token_version=1,
            )
        )
    app.dependency_overrides[get_pool] = lambda: pool
    return app


class CreateOpenPositionPool:
    def __init__(self) -> None:
        self.insert_args: tuple[object, ...] | None = None

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "INSERT INTO open_positions" in query
        self.insert_args = args
        return {
            **open_position_record(
                employment_type=str(args[1]),
                status=str(args[5]),
            ),
            "title": str(args[0]),
            "description": str(args[2]),
            "position": str(args[3]),
            "city": str(args[4]),
        }


class ListAdminOpenPositionsPool:
    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "SELECT count(*) AS total FROM open_positions" in query
        assert args == ("active", "part_time")
        return {"total": 11}

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert "status = $1::open_position_status" in query
        assert "employment_type = $2::employment_type" in query
        assert args == ("active", "part_time", 10, 10)
        return [open_position_record(employment_type="part_time")]


class PublicOpenPositionsPool:
    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert "status = $1::open_position_status" in query
        assert "employment_type = $2::employment_type" in query
        assert "ORDER BY created_at DESC, id DESC" in query
        assert args == ("active", "full_time", 2)
        return [
            open_position_record(),
            open_position_record(open_position_id=NEXT_OPEN_POSITION_ID),
        ]


class PublicOpenPositionNotFoundPool:
    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "status = $2::open_position_status" in query
        assert args == (OPEN_POSITION_ID, "active")
        return None


class UpdateOpenPositionPool:
    def __init__(self) -> None:
        self.update_args: tuple[object, ...] | None = None

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "UPDATE open_positions" in query
        self.update_args = args
        return open_position_record(employment_type=str(args[0]))


class DeleteOpenPositionPool:
    def __init__(self) -> None:
        self.deleted_id: object | None = None

    async def execute(self, query: str, *args: object) -> str:
        assert query == "DELETE FROM open_positions WHERE id = $1"
        self.deleted_id = args[0]
        return "DELETE 1"


def test_admin_can_create_open_position(monkeypatch: Any) -> None:
    pool = CreateOpenPositionPool()
    app = configure_test_app(monkeypatch, pool, admin=True)
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/admin/open-positions", json=open_position_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["employment_type"] == "full_time"
    assert response.json()["status"] == "active"
    assert response.json()["position"]["EN-US"] == "Delivery"
    assert pool.insert_args is not None
    assert json.loads(str(pool.insert_args[0])) == localized_text("Delivery Driver")


def test_admin_can_filter_and_paginate_open_positions(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, ListAdminOpenPositionsPool(), admin=True)
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/admin/open-positions"
                "?status=active&employment_type=part_time&page=2&limit=10"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total"] == 11
    assert response.json()["total_pages"] == 2
    assert response.json()["items"][0]["employment_type"] == "part_time"


def test_admin_open_position_patch_rejects_empty_payload(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, object(), admin=True)
    try:
        with TestClient(app) as client:
            response = client.patch(f"/api/v1/admin/open-positions/{OPEN_POSITION_ID}", json={})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_admin_can_update_open_position_employment_type(monkeypatch: Any) -> None:
    pool = UpdateOpenPositionPool()
    app = configure_test_app(monkeypatch, pool, admin=True)
    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/admin/open-positions/{OPEN_POSITION_ID}",
                json={"employment_type": "part_time"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["employment_type"] == "part_time"
    assert pool.update_args == ("part_time", OPEN_POSITION_ID)


def test_admin_can_delete_open_position(monkeypatch: Any) -> None:
    pool = DeleteOpenPositionPool()
    app = configure_test_app(monkeypatch, pool, admin=True)
    try:
        with TestClient(app) as client:
            response = client.delete(f"/api/v1/admin/open-positions/{OPEN_POSITION_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert pool.deleted_id == OPEN_POSITION_ID


def test_public_open_positions_are_localized_and_filterable(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, PublicOpenPositionsPool())
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/ru-ru/open-positions?employment_type=full_time&limit=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["title"] == "Delivery Driver RU"
    assert payload["items"][0]["description"] == "Deliver healthy meals. RU"
    assert payload["items"][0]["position"] == "Delivery RU"
    assert payload["items"][0]["city"] == "Yerevan RU"
    assert "status" not in payload["items"][0]
    assert decode_cursor(payload["next_cursor"]) == {
        "created_at": NOW.isoformat(),
        "id": str(OPEN_POSITION_ID),
    }


def test_public_open_position_read_hides_inactive_position(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, PublicOpenPositionNotFoundPool())
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/en-us/open-positions/{OPEN_POSITION_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "Open position not found"
