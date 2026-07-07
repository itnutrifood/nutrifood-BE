import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from backend.apps.common.pagination import decode_cursor, encode_cursor
from backend.config.database import get_pool
from fastapi.testclient import TestClient

CATEGORY_ID = UUID("00000000-0000-0000-0000-000000000001")
NEXT_CATEGORY_ID = UUID("00000000-0000-0000-0000-000000000002")
PRODUCT_ID = UUID("10000000-0000-0000-0000-000000000001")
SUBSCRIPTION_PLAN_ID = UUID("30000000-0000-0000-0000-000000000001")
NEXT_SUBSCRIPTION_PLAN_ID = UUID("30000000-0000-0000-0000-000000000002")
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


def localized_words(en_us: str) -> dict[str, list[str]]:
    return {
        "HY-AM": [f"{en_us} HY"],
        "EN-US": [en_us],
        "RU-RU": [f"{en_us} RU"],
    }


def category_record(
    *,
    category_id: UUID = CATEGORY_ID,
    slug: str = "healthy-bowls",
    sort_order: int = 10,
) -> dict[str, object]:
    return {
        "id": category_id,
        "parent_id": None,
        "slug": slug,
        "name": json.dumps(localized_text("Healthy Bowls")),
        "description": json.dumps({"EN-US": "Fresh meals"}),
        "status": "active",
        "sort_order": sort_order,
        "created_at": NOW,
        "updated_at": NOW,
    }


def product_record() -> dict[str, object]:
    return {
        "id": PRODUCT_ID,
        "slug": "mediterranean-bowl",
        "title": json.dumps(localized_text("Mediterranean Bowl")),
        "description": json.dumps(localized_text("Fresh bowl")),
        "images": json.dumps(
            [
                {
                    "url": "https://cdn.example.test/mediterranean-bowl.jpg",
                    "width": 1200,
                    "height": 900,
                    "size_bytes": 450_000,
                }
            ]
        ),
        "image_tags": json.dumps(localized_words("High Protein")),
        "text_tags": json.dumps(localized_words("bowls")),
        "serving_size": json.dumps({"EN-US": "400g"}),
        "readiness_time_minutes": 3,
        "price": Decimal("12.99"),
        "allergens": json.dumps(localized_words("Sesame")),
        "allergen_information": json.dumps({"EN-US": "Contains sesame."}),
        "storage_delivery": json.dumps({"EN-US": "Keep refrigerated."}),
        "created_at": NOW,
        "updated_at": NOW,
        "category_ids": [CATEGORY_ID],
    }


def subscription_record(
    *,
    subscription_plan_id: UUID = SUBSCRIPTION_PLAN_ID,
    slug: str = "protein-pack",
    price: Decimal = Decimal("129.00"),
    sort_order: int = 20,
) -> dict[str, object]:
    return {
        "id": subscription_plan_id,
        "slug": slug,
        "name": json.dumps(localized_text("Protein Pack")),
        "description": json.dumps({"EN-US": "High-protein meals"}),
        "price": price,
        "billing_interval": json.dumps(localized_text("week")),
        "meal_count_label": json.dumps({"EN-US": "7 meals"}),
        "is_popular": True,
        "status": "active",
        "sort_order": sort_order,
        "additional_info": json.dumps(localized_words("45g+ protein per meal")),
        "created_at": NOW,
        "updated_at": NOW,
    }


def configure_test_app(monkeypatch: Any, pool: object) -> Any:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    app.dependency_overrides[get_pool] = lambda: pool
    return app


class PublicCategoryListPool:
    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        if "count(*)" in query or "OFFSET" in query:
            raise AssertionError(f"Unexpected pagination query: {query}")

        assert "status = $1::category_status" in query
        assert "parent_id IS NULL" in query
        assert "ORDER BY sort_order, slug, id" in query
        assert args == ("active", 2)
        return [
            category_record(),
            category_record(
                category_id=NEXT_CATEGORY_ID,
                slug="juices",
                sort_order=20,
            ),
        ]


class PublicCategoryReadPool:
    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "FROM categories" in query
        assert "status = $2::category_status" in query
        assert args == (CATEGORY_ID, "active")
        return category_record()


class UnexpectedFetchPool:
    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        raise AssertionError(f"Unexpected query: {query} {args}")


class PublicProductListPool:
    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        if "count(*)" in query or "OFFSET" in query:
            raise AssertionError(f"Unexpected pagination query: {query}")

        assert "INNER JOIN categories AS c ON c.id = pc.category_id" in query
        assert "p.created_at < $3" in query
        assert args == (CATEGORY_ID, "active", NOW, PRODUCT_ID, 2)
        return [product_record()]


class PublicSubscriptionListPool:
    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        if "count(*)" in query or "OFFSET" in query:
            raise AssertionError(f"Unexpected pagination query: {query}")

        assert "status = $1::subscription_plan_status" in query
        assert "is_popular = $2" in query
        assert "ORDER BY sort_order, price, slug, id" in query
        assert args == ("active", True, 2)
        return [
            subscription_record(),
            subscription_record(
                subscription_plan_id=NEXT_SUBSCRIPTION_PLAN_ID,
                slug="family-pack",
                price=Decimal("199.00"),
                sort_order=30,
            ),
        ]


class PublicSubscriptionReadNotFoundPool:
    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "FROM subscription_plans" in query
        assert "status = $2::subscription_plan_status" in query
        assert args == (SUBSCRIPTION_PLAN_ID, "active")
        return None


def test_public_categories_use_cursor_pagination(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, PublicCategoryListPool())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/ru-ru/categories?root_only=true&limit=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["slug"] == "healthy-bowls"
    assert payload["items"][0]["name"] == "Healthy Bowls RU"
    assert payload["items"][0]["description"] is None
    assert payload["next_cursor"] is not None
    assert decode_cursor(str(payload["next_cursor"])) == {
        "sort_order": 10,
        "slug": "healthy-bowls",
        "id": str(CATEGORY_ID),
    }


def test_public_category_read_requires_active_category(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, PublicCategoryReadPool())

    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/hy-am/categories/{CATEGORY_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["id"] == str(CATEGORY_ID)
    assert response.json()["name"] == "Healthy Bowls HY"


def test_public_categories_reject_invalid_cursor(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, UnexpectedFetchPool())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/en-us/categories?cursor=not-a-cursor")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid cursor"


def test_public_products_filter_by_active_category_with_cursor(monkeypatch: Any) -> None:
    cursor = encode_cursor({"created_at": NOW, "id": str(PRODUCT_ID)})
    app = configure_test_app(monkeypatch, PublicProductListPool())

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/hy-am/products?category_id={CATEGORY_ID}&limit=1&cursor={cursor}"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["next_cursor"] is None
    assert payload["items"][0]["slug"] == "mediterranean-bowl"
    assert payload["items"][0]["title"] == "Mediterranean Bowl HY"
    assert payload["items"][0]["serving_size"] is None


def test_public_subscriptions_use_cursor_pagination(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, PublicSubscriptionListPool())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/en-us/subscriptions?is_popular=true&limit=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 1
    assert payload["items"][0]["slug"] == "protein-pack"
    assert payload["items"][0]["name"] == "Protein Pack"
    assert payload["items"][0]["additional_info"] == ["45g+ protein per meal"]
    assert decode_cursor(str(payload["next_cursor"])) == {
        "sort_order": 20,
        "price": "129.00",
        "slug": "protein-pack",
        "id": str(SUBSCRIPTION_PLAN_ID),
    }


def test_public_subscription_read_requires_active_plan(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, PublicSubscriptionReadNotFoundPool())

    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/en-us/subscriptions/{SUBSCRIPTION_PLAN_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "Subscription plan not found"


def test_public_routes_reject_unsupported_locale(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, UnexpectedFetchPool())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/es-es/categories")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported locale"
