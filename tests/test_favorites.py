import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from backend.apps.accounts.auth import UserIdentity, get_current_user
from backend.apps.common.pagination import decode_cursor
from backend.config.database import get_pool
from fastapi.testclient import TestClient

USER_ID = UUID("50000000-0000-0000-0000-000000000001")
PRODUCT_ID = UUID("10000000-0000-0000-0000-000000000001")
NEXT_PRODUCT_ID = UUID("10000000-0000-0000-0000-000000000002")
CATEGORY_ID = UUID("00000000-0000-0000-0000-000000000001")
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


def product_record(product_id: UUID, favorited_at: datetime) -> dict[str, object]:
    localized_text = {
        "HY-AM": "Միջերկրածովյան բոուլ",
        "EN-US": "Mediterranean Bowl",
        "RU-RU": "Средиземноморский боул",
    }
    return {
        "id": product_id,
        "slug": "mediterranean-bowl",
        "title": json.dumps(localized_text),
        "description": json.dumps(
            {
                "HY-AM": "Թարմ բոուլ",
                "EN-US": "Fresh bowl",
                "RU-RU": "Свежий боул",
            }
        ),
        "images": json.dumps([{"url": "https://cdn.example.test/bowl.jpg"}]),
        "image_tags": json.dumps({}),
        "text_tags": json.dumps({}),
        "serving_size": json.dumps({}),
        "readiness_time_minutes": 3,
        "price": Decimal("12.99"),
        "allergens": json.dumps({}),
        "allergen_information": json.dumps({}),
        "storage_delivery": json.dumps({}),
        "created_at": NOW,
        "updated_at": NOW,
        "category_ids": [CATEGORY_ID],
        "favorited_at": favorited_at,
    }


class FavoritePool:
    def __init__(
        self,
        *,
        product_exists: bool = True,
        missing_product_ids: list[UUID] | None = None,
    ) -> None:
        self.product_exists = product_exists
        self.missing_product_ids = missing_product_ids or []
        self.added: tuple[object, ...] | None = None
        self.bulk_added: tuple[object, ...] | None = None
        self.removed: tuple[object, ...] | None = None

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert "FROM user_favorite_products AS uf" in query
        assert "ORDER BY uf.created_at DESC, uf.product_id DESC" in query
        assert args == (USER_ID, 2)
        return [
            product_record(PRODUCT_ID, NOW),
            product_record(NEXT_PRODUCT_ID, NOW),
        ]

    async def fetchval(self, query: str, *args: object) -> object:
        if "requested_products" in query:
            assert "SELECT DISTINCT unnest($2::uuid[])" in query
            assert "(SELECT count(*) FROM matching_products)" in query
            self.bulk_added = args
            return self.missing_product_ids

        assert "ON CONFLICT (user_id, product_id) DO NOTHING" in query
        self.added = args
        return self.product_exists

    async def execute(self, query: str, *args: object) -> str:
        assert "DELETE FROM user_favorite_products" in query
        self.removed = args
        return "DELETE 1"


def configure_test_app(monkeypatch: Any, pool: object, *, authenticated: bool = True) -> Any:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    app.dependency_overrides[get_pool] = lambda: pool
    if authenticated:
        app.dependency_overrides[get_current_user] = current_user
    return app


def test_list_favorites_returns_localized_products_with_cursor(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, FavoritePool())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/en-us/favorites?limit=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 1
    assert payload["items"][0]["id"] == str(PRODUCT_ID)
    assert payload["items"][0]["title"] == "Mediterranean Bowl"
    assert decode_cursor(str(payload["next_cursor"])) == {
        "created_at": NOW.isoformat(),
        "product_id": str(PRODUCT_ID),
    }


def test_add_favorite_is_idempotent(monkeypatch: Any) -> None:
    pool = FavoritePool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.put(f"/api/v1/en-us/favorites/{PRODUCT_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert pool.added == (USER_ID, PRODUCT_ID)


def test_add_favorite_rejects_missing_product(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, FavoritePool(product_exists=False))

    try:
        with TestClient(app) as client:
            response = client.put(f"/api/v1/en-us/favorites/{PRODUCT_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "message": "One or more products were not found",
            "product_ids": [str(PRODUCT_ID)],
        }
    }


def test_add_favorites_accepts_offline_batch(monkeypatch: Any) -> None:
    pool = FavoritePool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/en-us/favorites",
                json={"product_ids": [str(PRODUCT_ID), str(NEXT_PRODUCT_ID)]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert pool.bulk_added == (USER_ID, [PRODUCT_ID, NEXT_PRODUCT_ID])


def test_add_favorites_reports_missing_products_atomically(monkeypatch: Any) -> None:
    pool = FavoritePool(missing_product_ids=[NEXT_PRODUCT_ID])
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/en-us/favorites",
                json={"product_ids": [str(PRODUCT_ID), str(NEXT_PRODUCT_ID)]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"]["product_ids"] == [str(NEXT_PRODUCT_ID)]


def test_remove_favorite_is_idempotent(monkeypatch: Any) -> None:
    pool = FavoritePool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.delete(f"/api/v1/en-us/favorites/{PRODUCT_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert pool.removed == (USER_ID, PRODUCT_ID)


def test_favorites_require_authentication(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, FavoritePool(), authenticated=False)

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/en-us/favorites")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
