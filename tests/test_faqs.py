import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from backend.apps.admin import auth as admin_auth_module
from backend.apps.common.pagination import decode_cursor
from backend.config.database import get_pool
from fastapi.testclient import TestClient

FAQ_ID = UUID("50000000-0000-0000-0000-000000000001")
NEXT_FAQ_ID = UUID("50000000-0000-0000-0000-000000000002")
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


def faq_record(
    *,
    faq_id: UUID = FAQ_ID,
    slug: str = "how-delivery-works",
    sort_order: int = 10,
    status: str = "active",
) -> dict[str, object]:
    return {
        "id": faq_id,
        "slug": slug,
        "question": json.dumps(localized_text("How does delivery work?")),
        "answer": json.dumps(localized_text("We deliver every weekday.")),
        "status": status,
        "sort_order": sort_order,
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


class CreateFAQPool:
    def __init__(self) -> None:
        self.insert_args: tuple[object, ...] | None = None

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "INSERT INTO faqs" in query
        self.insert_args = args
        return {
            **faq_record(slug=str(args[0]), sort_order=int(args[4])),
            "question": str(args[1]),
            "answer": str(args[2]),
            "status": str(args[3]),
        }


class ListAdminFAQPool:
    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "SELECT count(*) AS total FROM faqs" in query
        assert args == ("inactive",)
        return {"total": 21}

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert "status = $1::faq_status" in query
        assert "ORDER BY sort_order, slug, id" in query
        assert args == ("inactive", 10, 10)
        return [faq_record(status="inactive")]


class PublicFAQListPool:
    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert "status = $1::faq_status" in query
        assert "ORDER BY sort_order, slug, id" in query
        assert args == ("active", 2)
        return [
            faq_record(),
            faq_record(faq_id=NEXT_FAQ_ID, slug="payment-methods", sort_order=20),
        ]


class PublicFAQNotFoundPool:
    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "status = $2::faq_status" in query
        assert args == (FAQ_ID, "active")
        return None


class UnexpectedFetchPool:
    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        raise AssertionError(f"Unexpected query: {query} {args}")


def test_admin_can_create_localized_faq(monkeypatch: Any) -> None:
    pool = CreateFAQPool()
    app = configure_test_app(monkeypatch, pool, admin=True)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/faqs",
                json={
                    "slug": "how-delivery-works",
                    "question": localized_text("How does delivery work?"),
                    "answer": localized_text("We deliver every weekday."),
                    "sort_order": 10,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["status"] == "active"
    assert response.json()["question"]["EN-US"] == "How does delivery work?"
    assert pool.insert_args is not None
    assert json.loads(str(pool.insert_args[1])) == localized_text("How does delivery work?")


def test_admin_can_filter_and_paginate_faqs(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, ListAdminFAQPool(), admin=True)

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/admin/faqs?status=inactive&page=2&limit=10")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total"] == 21
    assert response.json()["total_pages"] == 3
    assert response.json()["items"][0]["status"] == "inactive"


def test_admin_faq_patch_rejects_empty_payload(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, object(), admin=True)

    try:
        with TestClient(app) as client:
            response = client.patch(f"/api/v1/admin/faqs/{FAQ_ID}", json={})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_public_faqs_are_localized_and_use_cursor_pagination(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, PublicFAQListPool())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/ru-ru/faqs?limit=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["question"] == "How does delivery work? RU"
    assert payload["items"][0]["answer"] == "We deliver every weekday. RU"
    assert "status" not in payload["items"][0]
    assert decode_cursor(payload["next_cursor"]) == {
        "sort_order": 10,
        "slug": "how-delivery-works",
        "id": str(FAQ_ID),
    }


def test_public_faq_read_hides_inactive_faq(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, PublicFAQNotFoundPool())

    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/en-us/faqs/{FAQ_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "FAQ not found"


def test_public_faqs_reject_invalid_cursor(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, UnexpectedFetchPool())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/en-us/faqs?cursor=invalid")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid cursor"
