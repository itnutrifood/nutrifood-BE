import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from backend.apps.admin import auth as admin_auth_module
from backend.config.database import get_pool
from fastapi.testclient import TestClient

SUBSCRIPTION_PLAN_ID = UUID("30000000-0000-0000-0000-000000000001")
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


def localized_info(en_us: str) -> dict[str, list[str]]:
    return {
        "HY-AM": [f"{en_us} HY"],
        "EN-US": [en_us],
        "RU-RU": [f"{en_us} RU"],
    }


def subscription_payload() -> dict[str, object]:
    return {
        "slug": "protein-pack",
        "name": localized_text("Protein Pack"),
        "description": {"EN-US": "High-protein meals for fitness goals"},
        "price": "129.00",
        "billing_interval": localized_text("week"),
        "meal_count_label": {"EN-US": "7 meals"},
        "is_popular": True,
        "status": "active",
        "sort_order": 20,
        "additional_info": localized_info("45g+ protein per meal"),
    }


def subscription_record(
    *,
    subscription_plan_id: UUID = SUBSCRIPTION_PLAN_ID,
    slug: str = "protein-pack",
    name: str | None = None,
    description: str | None = None,
    price: Decimal = Decimal("129.00"),
    billing_interval: str | None = None,
    meal_count_label: str | None = None,
    is_popular: bool = True,
    status: str = "active",
    sort_order: int = 20,
    additional_info: str | None = None,
) -> dict[str, object]:
    return {
        "id": subscription_plan_id,
        "slug": slug,
        "name": name or json.dumps(localized_text("Protein Pack")),
        "description": description or json.dumps({"EN-US": "High-protein meals"}),
        "price": price,
        "billing_interval": billing_interval or json.dumps(localized_text("week")),
        "meal_count_label": meal_count_label or json.dumps({"EN-US": "7 meals"}),
        "is_popular": is_popular,
        "status": status,
        "sort_order": sort_order,
        "additional_info": additional_info or json.dumps(localized_info("45g+ protein per meal")),
        "created_at": NOW,
        "updated_at": NOW,
    }


class CreateSubscriptionPlanPool:
    def __init__(self) -> None:
        self.insert_args: tuple[object, ...] | None = None

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "INSERT INTO subscription_plans" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        self.insert_args = args
        return subscription_record(
            slug=str(args[0]),
            name=str(args[1]),
            description=str(args[2]),
            price=args[3] if isinstance(args[3], Decimal) else Decimal(str(args[3])),
            billing_interval=str(args[4]),
            meal_count_label=str(args[5]),
            is_popular=bool(args[6]),
            status=str(args[7]),
            sort_order=int(args[8]),
            additional_info=str(args[9]),
        )


class ListSubscriptionPlanPool:
    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "SELECT count(*) AS total" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        assert args == ("active", True)
        return {"total": 101}

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        if "FROM subscription_plans" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        assert args == ("active", True, 50, 50)
        return [subscription_record()]


class UpdateSubscriptionPlanPool:
    def __init__(self) -> None:
        self.update_args: tuple[object, ...] | None = None

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "UPDATE subscription_plans" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        self.update_args = args
        price = args[0] if isinstance(args[0], Decimal) else Decimal(str(args[0]))
        return subscription_record(price=price)


class DeleteSubscriptionPlanPool:
    def __init__(self) -> None:
        self.deleted_subscription_plan_id: UUID | None = None

    async def execute(self, query: str, *args: object) -> str:
        if "DELETE FROM subscription_plans" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        self.deleted_subscription_plan_id = args[0] if isinstance(args[0], UUID) else None
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


def test_admin_can_create_subscription_plan(monkeypatch: Any) -> None:
    pool = CreateSubscriptionPlanPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/admin/subscriptions", json=subscription_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["slug"] == "protein-pack"
    assert response.json()["is_popular"] is True
    assert response.json()["additional_info"] == localized_info("45g+ protein per meal")
    assert pool.insert_args is not None
    assert json.loads(str(pool.insert_args[1])) == localized_text("Protein Pack")
    assert json.loads(str(pool.insert_args[9])) == localized_info("45g+ protein per meal")


def test_admin_can_list_subscription_plans(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, ListSubscriptionPlanPool())

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/admin/subscriptions?status=active&is_popular=true&page=2&limit=50"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total"] == 101
    assert response.json()["page"] == 2
    assert response.json()["limit"] == 50
    assert response.json()["total_pages"] == 3
    assert "offset" not in response.json()
    assert response.json()["items"][0]["slug"] == "protein-pack"


def test_admin_can_update_subscription_plan(monkeypatch: Any) -> None:
    pool = UpdateSubscriptionPlanPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/admin/subscriptions/{SUBSCRIPTION_PLAN_ID}",
                json={"price": "119.00"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert pool.update_args == (Decimal("119.00"), SUBSCRIPTION_PLAN_ID)


def test_admin_delete_subscription_plan_returns_no_content(monkeypatch: Any) -> None:
    pool = DeleteSubscriptionPlanPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.delete(f"/api/v1/admin/subscriptions/{SUBSCRIPTION_PLAN_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert pool.deleted_subscription_plan_id == SUBSCRIPTION_PLAN_ID
