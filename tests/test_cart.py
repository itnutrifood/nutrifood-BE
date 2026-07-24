import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from backend.apps.accounts.auth import UserIdentity, get_current_user
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
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        token_version=1,
        created_at=NOW,
        updated_at=NOW,
    )


def product_record(product_id: UUID, quantity: int) -> dict[str, object]:
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
        "quantity": quantity,
    }


class CartPool:
    def __init__(
        self,
        *,
        product_exists: bool = True,
        missing_product_ids: list[UUID] | None = None,
    ) -> None:
        self.product_exists = product_exists
        self.missing_product_ids = missing_product_ids or []
        self.upserted: tuple[object, ...] | None = None
        self.bulk_upserted: tuple[object, ...] | None = None
        self.removed: tuple[object, ...] | None = None
        self.cleared: tuple[object, ...] | None = None

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert "FROM user_cart_items AS ci" in query
        assert "ORDER BY ci.created_at DESC, ci.product_id DESC" in query
        assert args == (USER_ID,)
        return [
            product_record(PRODUCT_ID, 2),
            product_record(NEXT_PRODUCT_ID, 1),
        ]

    async def fetchval(self, query: str, *args: object) -> object:
        if "requested_products" in query:
            assert "unnest($2::uuid[], $3::integer[])" in query
            assert "(SELECT count(*) FROM matching_products)" in query
            assert "quantity = EXCLUDED.quantity" in query
            self.bulk_upserted = args
            return self.missing_product_ids

        assert "ON CONFLICT (user_id, product_id) DO UPDATE" in query
        assert "quantity = EXCLUDED.quantity" in query
        self.upserted = args
        return self.product_exists

    async def execute(self, query: str, *args: object) -> str:
        assert "DELETE FROM user_cart_items" in query
        if len(args) == 2:
            self.removed = args
        else:
            self.cleared = args
        return "DELETE 1"


def configure_test_app(monkeypatch: Any, pool: object, *, authenticated: bool = True) -> Any:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    app.dependency_overrides[get_pool] = lambda: pool
    if authenticated:
        app.dependency_overrides[get_current_user] = current_user
    return app


def test_read_cart_returns_localized_products_and_totals(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, CartPool())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/en-us/cart")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_quantity"] == 3
    assert payload["subtotal"] == "38.97"
    assert payload["items"][0]["quantity"] == 2
    assert payload["items"][0]["line_total"] == "25.98"
    assert payload["items"][0]["product"]["title"] == "Mediterranean Bowl"


def test_set_cart_item_is_idempotent(monkeypatch: Any) -> None:
    pool = CartPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.put(
                f"/api/v1/en-us/cart/{PRODUCT_ID}",
                json={"quantity": 3},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert pool.upserted == (USER_ID, PRODUCT_ID, 3)


def test_set_cart_item_rejects_missing_product(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, CartPool(product_exists=False))

    try:
        with TestClient(app) as client:
            response = client.put(
                f"/api/v1/en-us/cart/{PRODUCT_ID}",
                json={"quantity": 1},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"]["product_ids"] == [str(PRODUCT_ID)]


def test_set_cart_items_accepts_offline_batch(monkeypatch: Any) -> None:
    pool = CartPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/en-us/cart",
                json={
                    "items": [
                        {"product_id": str(PRODUCT_ID), "quantity": 2},
                        {"product_id": str(NEXT_PRODUCT_ID), "quantity": 4},
                    ]
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert pool.bulk_upserted == (
        USER_ID,
        [PRODUCT_ID, NEXT_PRODUCT_ID],
        [2, 4],
    )


def test_set_cart_items_reports_missing_products_atomically(monkeypatch: Any) -> None:
    pool = CartPool(missing_product_ids=[NEXT_PRODUCT_ID])
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/en-us/cart",
                json={
                    "items": [
                        {"product_id": str(PRODUCT_ID), "quantity": 2},
                        {"product_id": str(NEXT_PRODUCT_ID), "quantity": 4},
                    ]
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"]["product_ids"] == [str(NEXT_PRODUCT_ID)]


def test_set_cart_items_rejects_duplicate_products(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, CartPool())

    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/en-us/cart",
                json={
                    "items": [
                        {"product_id": str(PRODUCT_ID), "quantity": 2},
                        {"product_id": str(PRODUCT_ID), "quantity": 4},
                    ]
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_remove_cart_item_and_clear_cart_are_idempotent(monkeypatch: Any) -> None:
    pool = CartPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            remove_response = client.delete(f"/api/v1/en-us/cart/{PRODUCT_ID}")
            clear_response = client.delete("/api/v1/en-us/cart")
    finally:
        app.dependency_overrides.clear()

    assert remove_response.status_code == 204
    assert clear_response.status_code == 204
    assert pool.removed == (USER_ID, PRODUCT_ID)
    assert pool.cleared == (USER_ID,)


def test_cart_server_sync_requires_authentication(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, CartPool(), authenticated=False)

    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/en-us/cart",
                json={"items": [{"product_id": str(PRODUCT_ID), "quantity": 2}]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
