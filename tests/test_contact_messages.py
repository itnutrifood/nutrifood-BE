from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from backend.apps.admin import auth as admin_auth_module
from backend.config.database import get_pool
from fastapi.testclient import TestClient

MESSAGE_ID = UUID("60000000-0000-0000-0000-000000000001")
ADMIN_ID = UUID("40000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 1, 1, tzinfo=UTC)


class DummyPool:
    async def close(self) -> None:
        return None


async def create_dummy_pool() -> DummyPool:
    return DummyPool()


def contact_message_record(*, status: str = "unread") -> dict[str, object]:
    return {
        "id": MESSAGE_ID,
        "name": "Jane Doe",
        "email": "jane@example.com",
        "subject": "Delivery question",
        "message": "Can I change my delivery day?",
        "status": status,
        "created_at": NOW,
        "updated_at": NOW,
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


class CreateContactMessagePool:
    def __init__(self) -> None:
        self.insert_args: tuple[object, ...] | None = None

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "INSERT INTO contact_messages" in query
        self.insert_args = args
        return {
            **contact_message_record(),
            "name": str(args[0]),
            "email": str(args[1]),
            "subject": str(args[2]),
            "message": str(args[3]),
        }


class ListContactMessagesPool:
    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "SELECT count(*) AS total FROM contact_messages" in query
        assert args == ("unread",)
        return {"total": 12}

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert "status = $1::contact_message_status" in query
        assert "ORDER BY created_at DESC, id DESC" in query
        assert args == ("unread", 10, 10)
        return [contact_message_record()]


class UpdateContactMessagePool:
    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "UPDATE contact_messages" in query
        assert args == ("read", MESSAGE_ID)
        return contact_message_record(status="read")


def test_contact_message_is_stored_as_unread(monkeypatch: Any) -> None:
    pool = CreateContactMessagePool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/contact-us",
                json={
                    "name": " Jane Doe ",
                    "email": "Jane@EXAMPLE.COM",
                    "subject": " Delivery question ",
                    "message": " Can I change my delivery day? ",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["status"] == "unread"
    assert pool.insert_args == (
        "Jane Doe",
        "jane@example.com",
        "Delivery question",
        "Can I change my delivery day?",
    )


def test_contact_message_rejects_invalid_email(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, object())

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/contact-us",
                json={
                    "name": "Jane Doe",
                    "email": "not-an-email",
                    "subject": "Delivery question",
                    "message": "Can I change my delivery day?",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_admin_lists_unread_messages_newest_first(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, ListContactMessagesPool(), admin=True)

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/admin/contact-messages?status=unread&page=2&limit=10")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total"] == 12
    assert response.json()["total_pages"] == 2
    assert response.json()["items"][0]["status"] == "unread"


def test_admin_marks_contact_message_as_read(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, UpdateContactMessagePool(), admin=True)

    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/admin/contact-messages/{MESSAGE_ID}",
                json={"status": "read"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "read"
