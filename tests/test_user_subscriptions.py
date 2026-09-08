import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from backend.apps.accounts.auth import UserIdentity, get_current_user
from backend.config.database import get_pool
from backend.config.settings import Settings, get_settings
from fastapi.testclient import TestClient

USER_ID = UUID("50000000-0000-0000-0000-000000000001")
SUBSCRIPTION_ID = UUID("60000000-0000-0000-0000-000000000001")
PLAN_ID = UUID("30000000-0000-0000-0000-000000000001")
OTHER_PLAN_ID = UUID("30000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 1, 1, tzinfo=UTC)


class DummyPool:
    async def close(self) -> None:
        return None


async def create_dummy_pool() -> DummyPool:
    return DummyPool()


class AsyncContext:
    def __init__(self, value: object) -> None:
        self.value = value

    async def __aenter__(self) -> object:
        return self.value

    async def __aexit__(self, *args: object) -> None:
        return None


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


def subscription_record(*, plan_id: UUID = PLAN_ID) -> dict[str, object]:
    return {
        "id": SUBSCRIPTION_ID,
        "user_id": USER_ID,
        "subscription_plan_id": plan_id,
        "status": "active",
        "activation_source": "test_bypass",
        "started_at": NOW,
        "cancelled_at": None,
        "created_at": NOW,
        "updated_at": NOW,
    }


def plan_record(plan_id: UUID = PLAN_ID) -> dict[str, object]:
    localized_name = {
        "HY-AM": "Սպիտակուցային փաթեթ",
        "EN-US": "Protein Pack",
        "RU-RU": "Протеиновый набор",
    }
    localized_interval = {
        "HY-AM": "շաբաթ",
        "EN-US": "week",
        "RU-RU": "неделя",
    }
    return {
        "id": plan_id,
        "slug": "protein-pack",
        "name": json.dumps(localized_name),
        "description": json.dumps({"EN-US": "High-protein meals"}),
        "price": Decimal("129.00"),
        "billing_interval": json.dumps(localized_interval),
        "meal_count_label": json.dumps({"EN-US": "7 meals"}),
        "is_popular": True,
        "status": "active",
        "sort_order": 20,
        "additional_info": json.dumps({"EN-US": ["45g+ protein per meal"]}),
        "created_at": NOW,
        "updated_at": NOW,
    }


class UserSubscriptionPool:
    def __init__(
        self,
        *,
        current: dict[str, object] | None = None,
        plan_exists: bool = True,
    ) -> None:
        self.current = current
        self.plan_exists = plan_exists
        self.user_locked = False
        self.insert_args: tuple[object, ...] | None = None
        self.cancel_args: tuple[object, ...] | None = None

    def acquire(self) -> AsyncContext:
        return AsyncContext(self)

    def transaction(self) -> AsyncContext:
        return AsyncContext(self)

    async def fetchval(self, query: str, *args: object) -> object | None:
        if "FROM users" in query:
            assert "FOR UPDATE" in query
            assert args == (USER_ID,)
            self.user_locked = True
            return USER_ID

        assert "FROM subscription_plans" in query
        assert "FOR SHARE" in query
        assert self.user_locked
        assert args == (PLAN_ID, "active")
        return PLAN_ID if self.plan_exists else None

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "INSERT INTO user_subscriptions" in query:
            assert self.user_locked
            assert args == (USER_ID, PLAN_ID, "test_bypass")
            self.insert_args = args
            self.current = subscription_record()
            return self.current

        if "FROM user_subscriptions" in query:
            assert args == (USER_ID, "active")
            return self.current

        if "FROM subscription_plans" in query:
            plan_id = args[0]
            assert isinstance(plan_id, UUID)
            return plan_record(plan_id)

        raise AssertionError(f"Unexpected query: {query}")

    async def execute(self, query: str, *args: object) -> str:
        assert "UPDATE user_subscriptions" in query
        assert "cancelled_at = now()" in query
        self.cancel_args = args
        return "UPDATE 1"


def configure_test_app(
    monkeypatch: Any,
    pool: object,
    *,
    authenticated: bool = True,
    environment: str = "local",
) -> Any:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        environment=environment,
    )
    if authenticated:
        app.dependency_overrides[get_current_user] = current_user
    return app


def test_temporary_subscribe_creates_localized_subscription(monkeypatch: Any) -> None:
    pool = UserSubscriptionPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post(f"/api/v1/en-us/subscriptions/{PLAN_ID}/subscribe")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json() == {
        "id": str(SUBSCRIPTION_ID),
        "status": "active",
        "activation_source": "test_bypass",
        "started_at": NOW.isoformat().replace("+00:00", "Z"),
        "cancelled_at": None,
        "plan": {
            "id": str(PLAN_ID),
            "slug": "protein-pack",
            "name": "Protein Pack",
            "description": "High-protein meals",
            "price": "129.00",
            "billing_interval": "week",
            "meal_count_label": "7 meals",
            "is_popular": True,
            "status": "active",
            "sort_order": 20,
            "additional_info": ["45g+ protein per meal"],
            "created_at": NOW.isoformat().replace("+00:00", "Z"),
            "updated_at": NOW.isoformat().replace("+00:00", "Z"),
        },
        "created_at": NOW.isoformat().replace("+00:00", "Z"),
        "updated_at": NOW.isoformat().replace("+00:00", "Z"),
    }
    assert pool.insert_args == (USER_ID, PLAN_ID, "test_bypass")


def test_temporary_subscribe_is_idempotent_for_same_plan(monkeypatch: Any) -> None:
    pool = UserSubscriptionPool(current=subscription_record())
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post(f"/api/v1/en-us/subscriptions/{PLAN_ID}/subscribe")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["plan"]["id"] == str(PLAN_ID)
    assert pool.insert_args is None


def test_temporary_subscribe_rejects_a_second_active_plan(monkeypatch: Any) -> None:
    pool = UserSubscriptionPool(current=subscription_record(plan_id=OTHER_PLAN_ID))
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post(f"/api/v1/en-us/subscriptions/{PLAN_ID}/subscribe")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json() == {
        "detail": {
            "message": "User already has an active subscription",
            "subscription_plan_id": str(OTHER_PLAN_ID),
        }
    }
    assert pool.insert_args is None


def test_temporary_subscribe_requires_an_active_plan(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, UserSubscriptionPool(plan_exists=False))

    try:
        with TestClient(app) as client:
            response = client.post(f"/api/v1/en-us/subscriptions/{PLAN_ID}/subscribe")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Subscription plan not found"}


def test_current_subscription_can_be_read_and_cancelled(monkeypatch: Any) -> None:
    pool = UserSubscriptionPool(current=subscription_record())
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            read_response = client.get("/api/v1/en-us/subscriptions/current")
            cancel_response = client.delete(f"/api/v1/en-us/subscriptions/{PLAN_ID}/unsubscribe")
    finally:
        app.dependency_overrides.clear()

    assert read_response.status_code == 200
    assert read_response.json()["plan"]["id"] == str(PLAN_ID)
    assert cancel_response.status_code == 204
    assert cancel_response.content == b""
    assert pool.cancel_args == (USER_ID, PLAN_ID, "cancelled", "active")


def test_current_subscription_returns_not_found_when_absent(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, UserSubscriptionPool())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/en-us/subscriptions/current")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Active subscription not found"}


def test_temporary_subscribe_is_hidden_in_production(monkeypatch: Any) -> None:
    pool = UserSubscriptionPool()
    app = configure_test_app(monkeypatch, pool, environment="production")

    try:
        with TestClient(app) as client:
            response = client.post(f"/api/v1/en-us/subscriptions/{PLAN_ID}/subscribe")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert pool.insert_args is None


def test_subscription_mutations_require_authentication(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, object(), authenticated=False)

    try:
        with TestClient(app) as client:
            subscribe_response = client.post(f"/api/v1/en-us/subscriptions/{PLAN_ID}/subscribe")
            unsubscribe_response = client.delete(
                f"/api/v1/en-us/subscriptions/{PLAN_ID}/unsubscribe"
            )
    finally:
        app.dependency_overrides.clear()

    assert subscribe_response.status_code == 401
    assert unsubscribe_response.status_code == 401
