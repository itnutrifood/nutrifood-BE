from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from backend.apps.accounts.auth import UserIdentity, get_current_user
from backend.config.database import get_pool
from fastapi.testclient import TestClient

USER_ID = UUID("50000000-0000-0000-0000-000000000001")
ADDRESS_ID = UUID("70000000-0000-0000-0000-000000000001")
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


def address_record(**overrides: object) -> dict[str, object]:
    return {
        "id": ADDRESS_ID,
        "country": "Armenia",
        "region": "Yerevan",
        "city": "Yerevan",
        "street": "Northern Avenue",
        "building_number": "10/1",
        "entrance": "2",
        "floor": "5",
        "created_at": NOW,
        "updated_at": NOW,
        **overrides,
    }


class AddressPool:
    def __init__(
        self,
        *,
        record: dict[str, object] | None = None,
        address_exists: bool = True,
    ) -> None:
        self.record = record or address_record()
        self.address_exists = address_exists
        self.fetchrow_query: str | None = None
        self.fetchrow_args: tuple[object, ...] | None = None
        self.fetch_args: tuple[object, ...] | None = None
        self.delete_args: tuple[object, ...] | None = None

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.fetchrow_query = query
        self.fetchrow_args = args
        if not self.address_exists:
            return None

        if "INSERT INTO user_addresses" in query:
            return address_record(
                country=args[1],
                region=args[2],
                city=args[3],
                street=args[4],
                building_number=args[5],
                entrance=args[6],
                floor=args[7],
            )
        if "UPDATE user_addresses" in query:
            return {**self.record, "city": args[0], "entrance": args[1]}
        if "FROM user_addresses" in query:
            return self.record
        raise AssertionError(f"Unexpected query: {query}")

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert "FROM user_addresses" in query
        assert "WHERE user_id = $1" in query
        assert "ORDER BY created_at DESC, id DESC" in query
        self.fetch_args = args
        return [self.record]

    async def execute(self, query: str, *args: object) -> str:
        assert query == "DELETE FROM user_addresses WHERE id = $1 AND user_id = $2"
        self.delete_args = args
        return "DELETE 1" if self.address_exists else "DELETE 0"


def configure_test_app(monkeypatch: Any, pool: object, *, authenticated: bool = True) -> Any:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    app.dependency_overrides[get_pool] = lambda: pool
    if authenticated:
        app.dependency_overrides[get_current_user] = current_user
    return app


def test_create_address_defaults_country_to_armenia_and_trims_text(monkeypatch: Any) -> None:
    pool = AddressPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/users/addresses",
                json={
                    "region": "Yerevan",
                    "city": " Yerevan ",
                    "street": " Northern Avenue ",
                    "building_number": " 10/1 ",
                    "entrance": " 2 ",
                    "floor": " 5 ",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["country"] == "Armenia"
    assert response.json()["region"] == "Yerevan"
    assert pool.fetchrow_query is not None
    assert "$3::armenia_region" in pool.fetchrow_query
    assert pool.fetchrow_args == (
        USER_ID,
        "Armenia",
        "Yerevan",
        "Yerevan",
        "Northern Avenue",
        "10/1",
        "2",
        "5",
    )


def test_create_address_rejects_other_countries_invalid_regions_and_delivery_notes(
    monkeypatch: Any,
) -> None:
    pool = AddressPool()
    app = configure_test_app(monkeypatch, pool)
    valid_payload = {
        "region": "Yerevan",
        "city": "Yerevan",
        "street": "Northern Avenue",
        "building_number": "10/1",
    }

    try:
        with TestClient(app) as client:
            country_response = client.post(
                "/api/v1/users/addresses",
                json={**valid_payload, "country": "Georgia"},
            )
            region_response = client.post(
                "/api/v1/users/addresses",
                json={**valid_payload, "region": "Artsakh"},
            )
            notes_response = client.post(
                "/api/v1/users/addresses",
                json={**valid_payload, "delivery_notes": "Call on arrival"},
            )
    finally:
        app.dependency_overrides.clear()

    assert country_response.status_code == 422
    assert region_response.status_code == 422
    assert notes_response.status_code == 422
    assert pool.fetchrow_query is None


def test_list_addresses_returns_only_current_users_addresses(monkeypatch: Any) -> None:
    pool = AddressPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/users/addresses")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(ADDRESS_ID)
    assert pool.fetch_args == (USER_ID,)


def test_read_address_scopes_lookup_to_current_user(monkeypatch: Any) -> None:
    pool = AddressPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/users/addresses/{ADDRESS_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert pool.fetchrow_query is not None
    assert "WHERE id = $1 AND user_id = $2" in pool.fetchrow_query
    assert pool.fetchrow_args == (ADDRESS_ID, USER_ID)


def test_patch_address_updates_provided_fields_and_can_clear_optional_fields(
    monkeypatch: Any,
) -> None:
    pool = AddressPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/users/addresses/{ADDRESS_ID}",
                json={"city": "Gyumri", "entrance": None},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["city"] == "Gyumri"
    assert response.json()["entrance"] is None
    assert pool.fetchrow_query is not None
    assert "SET city = $1, entrance = $2" in pool.fetchrow_query
    assert "WHERE id = $3 AND user_id = $4" in pool.fetchrow_query
    assert pool.fetchrow_args == ("Gyumri", None, ADDRESS_ID, USER_ID)


def test_patch_address_rejects_empty_payload_and_null_required_field(monkeypatch: Any) -> None:
    pool = AddressPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            empty_response = client.patch(f"/api/v1/users/addresses/{ADDRESS_ID}", json={})
            null_response = client.patch(
                f"/api/v1/users/addresses/{ADDRESS_ID}",
                json={"street": None},
            )
    finally:
        app.dependency_overrides.clear()

    assert empty_response.status_code == 422
    assert null_response.status_code == 422
    assert pool.fetchrow_query is None


def test_missing_address_returns_not_found_for_read_update_and_delete(monkeypatch: Any) -> None:
    pool = AddressPool(address_exists=False)
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            read_response = client.get(f"/api/v1/users/addresses/{ADDRESS_ID}")
            update_response = client.patch(
                f"/api/v1/users/addresses/{ADDRESS_ID}",
                json={"floor": "4"},
            )
            delete_response = client.delete(f"/api/v1/users/addresses/{ADDRESS_ID}")
    finally:
        app.dependency_overrides.clear()

    assert read_response.status_code == 404
    assert update_response.status_code == 404
    assert delete_response.status_code == 404
    assert delete_response.json() == {"detail": "Address not found"}


def test_delete_address_is_scoped_to_current_user(monkeypatch: Any) -> None:
    pool = AddressPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.delete(f"/api/v1/users/addresses/{ADDRESS_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert pool.delete_args == (ADDRESS_ID, USER_ID)


def test_addresses_require_authentication(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, AddressPool(), authenticated=False)

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/users/addresses")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
