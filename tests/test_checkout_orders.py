import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from backend.apps.accounts.auth import UserIdentity, get_current_user
from backend.apps.admin import auth as admin_auth_module
from backend.config.database import get_pool
from fastapi.testclient import TestClient

USER_ID = UUID("50000000-0000-0000-0000-000000000001")
ADMIN_ID = UUID("40000000-0000-0000-0000-000000000001")
ADDRESS_ID = UUID("60000000-0000-0000-0000-000000000001")
ORDER_ID = UUID("70000000-0000-0000-0000-000000000001")
ORDER_ITEM_ID = UUID("71000000-0000-0000-0000-000000000001")
PRODUCT_ID = UUID("10000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 1, 1, tzinfo=UTC)
REQUESTED_DELIVERY_AT = datetime(2026, 9, 3, 14, 0, tzinfo=UTC)


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


def localized_title() -> dict[str, str]:
    return {
        "HY-AM": "Միջերկրածովյան բոուլ",
        "EN-US": "Mediterranean Bowl",
        "RU-RU": "Средиземноморский боул",
    }


def order_record(
    *,
    payment_method: str = "cash_on_delivery",
    request_fingerprint: str = "a" * 64,
    requested_delivery_at: datetime | None = REQUESTED_DELIVERY_AT,
) -> dict[str, object]:
    return {
        "id": ORDER_ID,
        "order_number": "NFUX6Q8N6LD",
        "user_id": USER_ID,
        "status": "pending",
        "payment_method": payment_method,
        "payment_status": "unpaid",
        "subtotal": Decimal("25.98"),
        "delivery_fee": Decimal("0.00"),
        "total": Decimal("25.98"),
        "currency": "USD",
        "customer_first_name": "Jane",
        "customer_last_name": "Doe",
        "customer_email": "jane@example.com",
        "contact_phone": "+37499123456",
        "delivery_address_id": ADDRESS_ID,
        "delivery_country": "Armenia",
        "delivery_region": "Yerevan",
        "delivery_city": "Yerevan",
        "delivery_street": "Northern Avenue",
        "delivery_building_number": "10/1",
        "delivery_entrance": "2",
        "delivery_floor": "5",
        "requested_delivery_at": requested_delivery_at,
        "delivery_notes": "Call on arrival",
        "request_fingerprint": request_fingerprint,
        "created_at": NOW,
        "updated_at": NOW,
    }


def order_item_record() -> dict[str, object]:
    return {
        "id": ORDER_ITEM_ID,
        "product_id": PRODUCT_ID,
        "product_slug": "mediterranean-bowl",
        "product_title": json.dumps(localized_title()),
        "unit_price": Decimal("12.99"),
        "quantity": 2,
        "line_total": Decimal("25.98"),
    }


class AsyncContext:
    def __init__(self, value: object) -> None:
        self.value = value

    async def __aenter__(self) -> object:
        return self.value

    async def __aexit__(self, *_args: object) -> None:
        return None


class CheckoutPool:
    def __init__(
        self,
        *,
        empty: bool = False,
        address_exists: bool = True,
        requested_delivery_at: datetime | None = REQUESTED_DELIVERY_AT,
    ) -> None:
        self.empty = empty
        self.address_exists = address_exists
        self.requested_delivery_at = requested_delivery_at
        self.stored_order: dict[str, object] | None = None
        self.idempotency_key: str | None = None
        self.order_insert_count = 0
        self.cart_read_count = 0
        self.deleted_product_ids: list[UUID] | None = None
        self.advisory_lock_count = 0

    def acquire(self) -> AsyncContext:
        return AsyncContext(self)

    def transaction(self) -> AsyncContext:
        return AsyncContext(self)

    async def fetchval(self, query: str, *args: object) -> None:
        assert "pg_advisory_xact_lock" in query
        assert args == (str(USER_ID),)
        self.advisory_lock_count += 1

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "o.idempotency_key" in query:
            assert args[0] == USER_ID
            if self.idempotency_key == args[1]:
                return self.stored_order
            return None
        if "FROM user_addresses AS a" in query:
            assert args == (ADDRESS_ID, USER_ID)
            if not self.address_exists:
                return None
            return {
                "id": ADDRESS_ID,
                "country": "Armenia",
                "region": "Yerevan",
                "city": "Yerevan",
                "street": "Northern Avenue",
                "building_number": "10/1",
                "entrance": "2",
                "floor": "5",
                "first_name": "Jane",
                "last_name": "Doe",
                "email": "jane@example.com",
            }
        if "INSERT INTO orders" in query:
            assert args[0] == USER_ID
            assert args[1] in {"cash_on_delivery", "pos"}
            assert args[2] == Decimal("25.98")
            assert args[3] == "USD"
            assert args[8] == ADDRESS_ID
            assert args[16] == self.requested_delivery_at
            assert args[18] == "checkout-attempt-1"
            self.idempotency_key = str(args[18])
            self.stored_order = order_record(
                payment_method=str(args[1]),
                request_fingerprint=str(args[19]),
                requested_delivery_at=args[16],  # type: ignore[arg-type]
            )
            self.order_insert_count += 1
            return self.stored_order
        raise AssertionError(f"Unexpected query: {query}")

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        if "FROM user_cart_items AS ci" in query:
            assert args == (USER_ID,)
            assert "FOR UPDATE OF ci" in query
            assert "FOR SHARE OF p" in query
            self.cart_read_count += 1
            if self.empty:
                return []
            return [
                {
                    "product_id": PRODUCT_ID,
                    "quantity": 2,
                    "slug": "mediterranean-bowl",
                    "title": json.dumps(localized_title()),
                    "price": Decimal("12.99"),
                }
            ]
        if "INSERT INTO order_items" in query:
            assert args[0] == ORDER_ID
            assert args[1] == [PRODUCT_ID]
            assert args[4] == [Decimal("12.99")]
            assert args[5] == [2]
            return [order_item_record()]
        if "FROM order_items AS oi" in query:
            assert args == (ORDER_ID,)
            return [order_item_record()]
        raise AssertionError(f"Unexpected query: {query}")

    async def execute(self, query: str, *args: object) -> str:
        assert "DELETE FROM user_cart_items" in query
        assert args[0] == USER_ID
        self.deleted_product_ids = list(args[1])  # type: ignore[arg-type]
        return "DELETE 1"


class OrderPool:
    def __init__(self) -> None:
        self.count_query: str | None = None
        self.count_args: tuple[object, ...] | None = None
        self.list_query: str | None = None
        self.list_args: tuple[object, ...] | None = None
        self.detail_query: str | None = None
        self.detail_args: tuple[object, ...] | None = None

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "count(*) AS total" in query:
            self.count_query = query
            self.count_args = args
            return {"total": 1}
        if "FROM orders AS o" in query:
            self.detail_query = query
            self.detail_args = args
            return order_record(payment_method="pos")
        raise AssertionError(f"Unexpected query: {query}")

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        if "FROM order_items AS oi" in query:
            assert args == (ORDER_ID,)
            return [order_item_record()]
        if "FROM orders AS o" in query:
            self.list_query = query
            self.list_args = args
            return [order_record(payment_method="pos")]
        raise AssertionError(f"Unexpected query: {query}")


def configure_test_app(
    monkeypatch: Any,
    pool: object,
    *,
    authenticated: bool = True,
    admin_authenticated: bool = False,
) -> Any:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    app.dependency_overrides[get_pool] = lambda: pool
    if authenticated:
        app.dependency_overrides[get_current_user] = current_user
    if admin_authenticated:
        app.dependency_overrides[admin_auth_module.admin_auth] = lambda: (
            admin_auth_module.AdminUser(
                id=ADMIN_ID,
                username="admin@mail.com",
                token_version=1,
            )
        )
    return app


def place_order_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "address_id": str(ADDRESS_ID),
        "payment_method": "cash_on_delivery",
        "contact_phone": "+37499123456",
        "requested_delivery_at": "2026-09-03T14:00:00Z",
        "delivery_notes": "Call on arrival",
    }
    payload.update(changes)
    return payload


def test_place_order_snapshots_server_totals_clears_cart_and_replays_safely(
    monkeypatch: Any,
) -> None:
    pool = CheckoutPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            first_response = client.post(
                "/api/v1/checkout/orders",
                headers={"Idempotency-Key": "checkout-attempt-1"},
                json=place_order_payload(),
            )
            replay_response = client.post(
                "/api/v1/checkout/orders",
                headers={"Idempotency-Key": "checkout-attempt-1"},
                json=place_order_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert first_response.status_code == 201
    assert replay_response.status_code == 201
    assert first_response.json() == replay_response.json()
    assert first_response.json()["order_number"] == "NFUX6Q8N6LD"
    assert first_response.json()["subtotal"] == "25.98"
    assert first_response.json()["payment_status"] == "unpaid"
    assert first_response.json()["requested_delivery_at"] == "2026-09-03T14:00:00Z"
    assert first_response.json()["items"][0]["product_title"]["EN-US"] == ("Mediterranean Bowl")
    assert pool.order_insert_count == 1
    assert pool.cart_read_count == 1
    assert pool.deleted_product_ids == [PRODUCT_ID]
    assert pool.advisory_lock_count == 2


def test_place_order_rejects_requested_delivery_at_without_timezone(monkeypatch: Any) -> None:
    pool = CheckoutPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/checkout/orders",
                headers={"Idempotency-Key": "checkout-attempt-1"},
                json=place_order_payload(requested_delivery_at="2026-09-03T14:00:00"),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert pool.order_insert_count == 0


def test_place_order_accepts_null_requested_delivery_at_for_asap(monkeypatch: Any) -> None:
    pool = CheckoutPool(requested_delivery_at=None)
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/checkout/orders",
                headers={"Idempotency-Key": "checkout-attempt-1"},
                json=place_order_payload(requested_delivery_at=None),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["requested_delivery_at"] is None


def test_place_order_rejects_reusing_key_for_different_request(monkeypatch: Any) -> None:
    pool = CheckoutPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            first_response = client.post(
                "/api/v1/checkout/orders",
                headers={"Idempotency-Key": "checkout-attempt-1"},
                json=place_order_payload(),
            )
            conflict_response = client.post(
                "/api/v1/checkout/orders",
                headers={"Idempotency-Key": "checkout-attempt-1"},
                json=place_order_payload(delivery_notes="Leave at the door"),
            )
    finally:
        app.dependency_overrides.clear()

    assert first_response.status_code == 201
    assert conflict_response.status_code == 409
    assert "different request" in conflict_response.json()["detail"]
    assert pool.order_insert_count == 1


def test_place_order_validates_supported_payment_address_cart_and_headers(
    monkeypatch: Any,
) -> None:
    pool = CheckoutPool(empty=True)
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            online_response = client.post(
                "/api/v1/checkout/orders",
                headers={"Idempotency-Key": "checkout-attempt-1"},
                json=place_order_payload(payment_method="online_payment"),
            )
            missing_key_response = client.post(
                "/api/v1/checkout/orders",
                json=place_order_payload(),
            )
            empty_response = client.post(
                "/api/v1/checkout/orders",
                headers={"Idempotency-Key": "checkout-attempt-1"},
                json=place_order_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert online_response.status_code == 422
    assert missing_key_response.status_code == 422
    assert empty_response.status_code == 409
    assert empty_response.json() == {"detail": "Cannot place an order with an empty cart"}

    address_pool = CheckoutPool(address_exists=False)
    app = configure_test_app(monkeypatch, address_pool)
    try:
        with TestClient(app) as client:
            address_response = client.post(
                "/api/v1/checkout/orders",
                headers={"Idempotency-Key": "checkout-attempt-1"},
                json=place_order_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert address_response.status_code == 404
    assert address_response.json() == {"detail": "Delivery address not found"}


def test_checkout_requires_authentication(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, CheckoutPool(), authenticated=False)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/checkout/orders",
                headers={"Idempotency-Key": "checkout-attempt-1"},
                json=place_order_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_user_order_history_is_scoped_and_detail_keeps_snapshots(monkeypatch: Any) -> None:
    pool = OrderPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            list_response = client.get("/api/v1/orders?status=pending&page=2&limit=10")
            detail_response = client.get(f"/api/v1/orders/{ORDER_ID}")
    finally:
        app.dependency_overrides.clear()

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["payment_method"] == "pos"
    assert pool.count_query is not None and "o.user_id = $1" in pool.count_query
    assert pool.count_args == (USER_ID, "pending")
    assert pool.list_args == (USER_ID, "pending", 10, 10)
    assert detail_response.status_code == 200
    assert detail_response.json()["delivery_address"]["street"] == "Northern Avenue"
    assert pool.detail_query is not None and "o.user_id = $2" in pool.detail_query
    assert pool.detail_args == (ORDER_ID, USER_ID)


def test_admin_can_see_all_orders_and_filter_them(monkeypatch: Any) -> None:
    pool = OrderPool()
    app = configure_test_app(monkeypatch, pool, admin_authenticated=True)

    try:
        with TestClient(app) as client:
            list_response = client.get("/api/v1/admin/orders?status=pending&payment_method=pos")
            detail_response = client.get(f"/api/v1/admin/orders/{ORDER_ID}")
    finally:
        app.dependency_overrides.clear()

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["customer_email"] == "jane@example.com"
    assert pool.count_query is not None and "o.user_id" not in pool.count_query
    assert pool.count_args == ("pending", "pos")
    assert pool.list_args == ("pending", "pos", 100, 0)
    assert detail_response.status_code == 200
    assert pool.detail_query is not None and "o.user_id =" not in pool.detail_query
    assert pool.detail_args == (ORDER_ID,)
