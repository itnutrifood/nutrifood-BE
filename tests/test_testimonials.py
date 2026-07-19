from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from backend.apps.admin import auth as admin_auth_module
from backend.apps.common.pagination import decode_cursor
from backend.config.database import get_pool
from fastapi.testclient import TestClient

TESTIMONIAL_ID = UUID("70000000-0000-0000-0000-000000000001")
NEXT_TESTIMONIAL_ID = UUID("70000000-0000-0000-0000-000000000002")
ADMIN_ID = UUID("40000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 1, 1, tzinfo=UTC)


class DummyPool:
    async def close(self) -> None:
        return None


async def create_dummy_pool() -> DummyPool:
    return DummyPool()


def sample_testimonial_record(
    *,
    testimonial_id: UUID = TESTIMONIAL_ID,
    status: str = "active",
    sort_order: int = 10,
    photo_url: str | None = "https://cdn.example.test/jane.jpg",
) -> dict[str, object]:
    return {
        "id": testimonial_id,
        "first_name": "Jane",
        "last_name": "Doe",
        "author_title": "Fitness Enthusiast",
        "photo_url": photo_url,
        "review": "NutriFood makes healthy eating easy.",
        "rating": 5,
        "status": status,
        "sort_order": sort_order,
        "created_at": NOW,
        "updated_at": NOW,
    }


def sample_testimonial_payload() -> dict[str, object]:
    return {
        "first_name": "Jane",
        "last_name": "Doe",
        "author_title": "Fitness Enthusiast",
        "photo_url": "https://cdn.example.test/jane.jpg",
        "review": "NutriFood makes healthy eating easy.",
        "rating": 5,
        "sort_order": 10,
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


class CreateTestimonialPool:
    def __init__(self) -> None:
        self.insert_args: tuple[object, ...] | None = None

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "INSERT INTO testimonials" in query
        self.insert_args = args
        return {
            **sample_testimonial_record(
                status=str(args[6]),
                sort_order=int(args[7]),
                photo_url=str(args[3]) if args[3] is not None else None,
            ),
            "first_name": str(args[0]),
            "last_name": str(args[1]),
            "author_title": str(args[2]),
            "review": str(args[4]),
            "rating": int(args[5]),
        }


class ListAdminTestimonialsPool:
    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "SELECT count(*) AS total FROM testimonials" in query
        assert args == ("inactive",)
        return {"total": 12}

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert "status = $1::testimonial_status" in query
        assert "ORDER BY sort_order, created_at DESC, id DESC" in query
        assert args == ("inactive", 10, 10)
        return [sample_testimonial_record(status="inactive")]


class UpdateTestimonialPool:
    def __init__(self) -> None:
        self.update_args: tuple[object, ...] | None = None

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "UPDATE testimonials" in query
        assert "photo_url = $1" in query
        assert "rating = $2" in query
        self.update_args = args
        return {**sample_testimonial_record(photo_url=None), "rating": int(args[1])}


class DeleteTestimonialPool:
    def __init__(self) -> None:
        self.deleted_id: object | None = None

    async def execute(self, query: str, *args: object) -> str:
        assert query == "DELETE FROM testimonials WHERE id = $1"
        self.deleted_id = args[0]
        return "DELETE 1"


class PublicTestimonialsPool:
    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert "status = $1::testimonial_status" in query
        assert "ORDER BY sort_order, created_at DESC, id DESC" in query
        assert args == ("active", 2)
        return [
            sample_testimonial_record(),
            sample_testimonial_record(testimonial_id=NEXT_TESTIMONIAL_ID, sort_order=20),
        ]


class PublicTestimonialNotFoundPool:
    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "status = $2::testimonial_status" in query
        assert args == (TESTIMONIAL_ID, "active")
        return None


def test_admin_can_create_single_language_testimonial(monkeypatch: Any) -> None:
    pool = CreateTestimonialPool()
    app = configure_test_app(monkeypatch, pool, admin=True)

    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/admin/testimonials", json=sample_testimonial_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["author_title"] == "Fitness Enthusiast"
    assert response.json()["status"] == "active"
    assert response.json()["rating"] == 5
    assert pool.insert_args is not None


def test_admin_can_filter_and_paginate_testimonials(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, ListAdminTestimonialsPool(), admin=True)

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/admin/testimonials?status=inactive&page=2&limit=10")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total"] == 12
    assert response.json()["total_pages"] == 2
    assert response.json()["items"][0]["status"] == "inactive"


def test_admin_can_clear_photo_and_update_rating(monkeypatch: Any) -> None:
    pool = UpdateTestimonialPool()
    app = configure_test_app(monkeypatch, pool, admin=True)

    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/admin/testimonials/{TESTIMONIAL_ID}",
                json={"photo_url": None, "rating": 4},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["photo_url"] is None
    assert response.json()["rating"] == 4
    assert pool.update_args == (None, 4, TESTIMONIAL_ID)


def test_admin_can_delete_testimonial(monkeypatch: Any) -> None:
    pool = DeleteTestimonialPool()
    app = configure_test_app(monkeypatch, pool, admin=True)

    try:
        with TestClient(app) as client:
            response = client.delete(f"/api/v1/admin/testimonials/{TESTIMONIAL_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert pool.deleted_id == TESTIMONIAL_ID


def test_testimonial_rating_must_be_between_one_and_five(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, object(), admin=True)
    payload = sample_testimonial_payload()
    payload["rating"] = 6

    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/admin/testimonials", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_public_testimonials_use_cursor_pagination(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, PublicTestimonialsPool())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/testimonials?limit=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["first_name"] == "Jane"
    assert payload["items"][0]["photo_url"] == "https://cdn.example.test/jane.jpg"
    assert "status" not in payload["items"][0]
    assert decode_cursor(payload["next_cursor"]) == {
        "sort_order": 10,
        "created_at": NOW.isoformat(),
        "id": str(TESTIMONIAL_ID),
    }


def test_public_testimonial_read_hides_inactive_entries(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, PublicTestimonialNotFoundPool())

    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/testimonials/{TESTIMONIAL_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Testimonial not found"}
