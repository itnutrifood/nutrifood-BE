from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from backend.apps.accounts.auth import UserIdentity, get_current_user
from backend.apps.users.addresses.enums import ArmeniaRegion, Country
from backend.apps.users.addresses.exceptions import (
    AddressGeocodingNotConfiguredError,
    InvalidAddressLocationError,
)
from backend.apps.users.addresses.geocoding import ResolvedAddress, get_address_geocoder
from backend.apps.users.addresses.schemas import AddressLocation
from backend.config.database import get_pool
from fastapi.testclient import TestClient

USER_ID = UUID("50000000-0000-0000-0000-000000000001")
ADDRESS_ID = UUID("70000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 1, 1, tzinfo=UTC)
LATITUDE = 40.1811
LONGITUDE = 44.5136


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


def resolved_address(**overrides: object) -> ResolvedAddress:
    values: dict[str, object] = {
        "country": Country.ARMENIA,
        "region": ArmeniaRegion.YEREVAN,
        "city": "Yerevan",
        "street": "Northern Avenue",
        "building_number": "10/1",
        "formatted_address": "Armenia, Yerevan, Northern Avenue, 10/1",
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "provider_uri": "ymapsbm1://geo?data=test",
        "geocode_kind": "house",
        "geocode_precision": "exact",
    }
    values.update(overrides)
    return ResolvedAddress(**values)  # type: ignore[arg-type]


def address_record(**overrides: object) -> dict[str, object]:
    return {
        "id": ADDRESS_ID,
        "label": "Home",
        "country": "Armenia",
        "region": "Yerevan",
        "city": "Yerevan",
        "street": "Northern Avenue",
        "building_number": "10/1",
        "entrance": "2",
        "floor": "5",
        "apartment": "17",
        "latitude": Decimal(str(LATITUDE)),
        "longitude": Decimal(str(LONGITUDE)),
        "formatted_address": "Armenia, Yerevan, Northern Avenue, 10/1",
        "location_source": "yandex",
        "provider_uri": "ymapsbm1://geo?data=test",
        "geocode_kind": "house",
        "geocode_precision": "exact",
        "is_default": False,
        "created_at": NOW,
        "updated_at": NOW,
        **overrides,
    }


class FakeGeocoder:
    def __init__(
        self,
        result: ResolvedAddress | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or resolved_address()
        self.error = error
        self.calls: list[AddressLocation] = []

    async def reverse_geocode(self, location: AddressLocation) -> ResolvedAddress:
        self.calls.append(location)
        if self.error is not None:
            raise self.error
        return self.result


class AsyncContext:
    def __init__(self, value: object) -> None:
        self.value = value

    async def __aenter__(self) -> object:
        return self.value

    async def __aexit__(self, *_args: object) -> None:
        return None


class AddressPool:
    def __init__(
        self,
        *,
        record: dict[str, object] | None = None,
        address_exists: bool = True,
    ) -> None:
        self.record = record if record is not None else address_record()
        self.address_exists = address_exists
        self.fetchrow_query: str | None = None
        self.fetchrow_args: tuple[object, ...] | None = None
        self.fetch_args: tuple[object, ...] | None = None
        self.delete_args: tuple[object, ...] | None = None
        self.cleared_default_args: tuple[object, ...] | None = None
        self.advisory_lock_count = 0
        self.transaction_count = 0

    def acquire(self) -> AsyncContext:
        return AsyncContext(self)

    def transaction(self) -> AsyncContext:
        self.transaction_count += 1
        return AsyncContext(self)

    async def fetchval(self, query: str, *args: object) -> None:
        assert "pg_advisory_xact_lock" in query
        assert args == (str(USER_ID),)
        self.advisory_lock_count += 1

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
                apartment=args[8],
                latitude=args[9],
                longitude=args[10],
                formatted_address=args[11],
                location_source=args[12],
                provider_uri=args[13],
                geocode_kind=args[14],
                geocode_precision=args[15],
                label=args[16],
                is_default=args[17],
            )
        if "UPDATE user_addresses" in query:
            updated_record = dict(self.record)
            if "country = $1" in query:
                updated_record.update(
                    country=args[0],
                    region=args[1],
                    city=args[2],
                    street=args[3],
                    building_number=args[4],
                    latitude=args[5],
                    longitude=args[6],
                    formatted_address=args[7],
                    location_source=args[8],
                    provider_uri=args[9],
                    geocode_kind=args[10],
                    geocode_precision=args[11],
                )
            if "entrance = $1" in query:
                updated_record["entrance"] = args[0]
            if "floor = $2" in query:
                updated_record["floor"] = args[1]
            if "label = $1" in query:
                updated_record["label"] = args[0]
            if "is_default = $1" in query:
                updated_record["is_default"] = args[0]
            return updated_record
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
        if "SET is_default = FALSE" in query:
            self.cleared_default_args = args
            return "UPDATE 1"
        assert query == "DELETE FROM user_addresses WHERE id = $1 AND user_id = $2"
        self.delete_args = args
        return "DELETE 1" if self.address_exists else "DELETE 0"


def configure_test_app(
    monkeypatch: Any,
    pool: object,
    geocoder: FakeGeocoder | None = None,
    *,
    authenticated: bool = True,
) -> Any:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_address_geocoder] = lambda: geocoder or FakeGeocoder()
    if authenticated:
        app.dependency_overrides[get_current_user] = current_user
    return app


def test_resolve_address_returns_normalized_yandex_preview(monkeypatch: Any) -> None:
    geocoder = FakeGeocoder()
    app = configure_test_app(monkeypatch, AddressPool(), geocoder)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/users/addresses/resolve",
                json={"latitude": LATITUDE, "longitude": LONGITUDE},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "country": "Armenia",
        "region": "Yerevan",
        "city": "Yerevan",
        "street": "Northern Avenue",
        "building_number": "10/1",
        "formatted_address": "Armenia, Yerevan, Northern Avenue, 10/1",
        "location": {"latitude": LATITUDE, "longitude": LONGITUDE},
        "geocode_precision": "exact",
    }
    assert geocoder.calls == [AddressLocation(latitude=LATITUDE, longitude=LONGITUDE)]


def test_create_address_resolves_location_and_trims_delivery_details(monkeypatch: Any) -> None:
    pool = AddressPool()
    geocoder = FakeGeocoder()
    app = configure_test_app(monkeypatch, pool, geocoder)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/users/addresses",
                json={
                    "location": {"latitude": LATITUDE, "longitude": LONGITUDE},
                    "label": "My sweet home",
                    "entrance": " 2 ",
                    "floor": " 5 ",
                    "apartment": " 17 ",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["formatted_address"] == ("Armenia, Yerevan, Northern Avenue, 10/1")
    assert response.json()["location"] == {"latitude": LATITUDE, "longitude": LONGITUDE}
    assert response.json()["location_source"] == "yandex"
    assert response.json()["label"] == "My sweet home"
    assert response.json()["apartment"] == "17"
    assert geocoder.calls == [AddressLocation(latitude=LATITUDE, longitude=LONGITUDE)]
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
        "17",
        Decimal(str(LATITUDE)),
        Decimal(str(LONGITUDE)),
        "Armenia, Yerevan, Northern Avenue, 10/1",
        "yandex",
        "ymapsbm1://geo?data=test",
        "house",
        "exact",
        "My sweet home",
        False,
    )


def test_create_default_address_replaces_previous_default(monkeypatch: Any) -> None:
    pool = AddressPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/users/addresses",
                json={
                    "location": {"latitude": LATITUDE, "longitude": LONGITUDE},
                    "is_default": True,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["label"] is None
    assert response.json()["is_default"] is True
    assert pool.advisory_lock_count == 1
    assert pool.transaction_count == 1
    assert pool.cleared_default_args == (USER_ID,)


def test_create_rejects_manual_address_fields_and_invalid_coordinates(monkeypatch: Any) -> None:
    pool = AddressPool()
    geocoder = FakeGeocoder()
    app = configure_test_app(monkeypatch, pool, geocoder)

    try:
        with TestClient(app) as client:
            manual_response = client.post(
                "/api/v1/users/addresses",
                json={
                    "location": {"latitude": LATITUDE, "longitude": LONGITUDE},
                    "city": "Yerevan",
                },
            )
            coordinates_response = client.post(
                "/api/v1/users/addresses",
                json={"location": {"latitude": 91, "longitude": LONGITUDE}},
            )
            long_label_response = client.post(
                "/api/v1/users/addresses",
                json={
                    "location": {"latitude": LATITUDE, "longitude": LONGITUDE},
                    "label": "x" * 33,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert manual_response.status_code == 422
    assert coordinates_response.status_code == 422
    assert long_label_response.status_code == 422
    assert geocoder.calls == []
    assert pool.fetchrow_query is None


def test_resolve_maps_geocoding_errors_to_safe_api_responses(monkeypatch: Any) -> None:
    app = configure_test_app(
        monkeypatch,
        AddressPool(),
        FakeGeocoder(error=InvalidAddressLocationError("Select a building")),
    )
    try:
        with TestClient(app) as client:
            invalid_response = client.post(
                "/api/v1/users/addresses/resolve",
                json={"latitude": LATITUDE, "longitude": LONGITUDE},
            )
    finally:
        app.dependency_overrides.clear()

    assert invalid_response.status_code == 422
    assert invalid_response.json() == {"detail": "Select a building"}

    app = configure_test_app(
        monkeypatch,
        AddressPool(),
        FakeGeocoder(error=AddressGeocodingNotConfiguredError()),
    )
    try:
        with TestClient(app) as client:
            unavailable_response = client.post(
                "/api/v1/users/addresses/resolve",
                json={"latitude": LATITUDE, "longitude": LONGITUDE},
            )
    finally:
        app.dependency_overrides.clear()

    assert unavailable_response.status_code == 503
    assert unavailable_response.json() == {"detail": "Address lookup is not configured"}


def test_list_addresses_supports_yandex_and_legacy_manual_rows(monkeypatch: Any) -> None:
    yandex_pool = AddressPool()
    app = configure_test_app(monkeypatch, yandex_pool)
    try:
        with TestClient(app) as client:
            yandex_response = client.get("/api/v1/users/addresses")
    finally:
        app.dependency_overrides.clear()

    assert yandex_response.status_code == 200
    assert yandex_response.json()[0]["location"] == {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
    }
    assert yandex_response.json()[0]["label"] == "Home"
    assert yandex_pool.fetch_args == (USER_ID,)

    legacy_pool = AddressPool(
        record=address_record(
            label=None,
            apartment=None,
            latitude=None,
            longitude=None,
            formatted_address=None,
            location_source="manual",
            provider_uri=None,
            geocode_kind=None,
            geocode_precision=None,
        )
    )
    app = configure_test_app(monkeypatch, legacy_pool)
    try:
        with TestClient(app) as client:
            legacy_response = client.get("/api/v1/users/addresses")
    finally:
        app.dependency_overrides.clear()

    assert legacy_response.status_code == 200
    assert legacy_response.json()[0]["location"] is None
    assert legacy_response.json()[0]["location_source"] == "manual"


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


def test_patch_delivery_details_does_not_call_yandex_and_can_clear_fields(
    monkeypatch: Any,
) -> None:
    pool = AddressPool()
    geocoder = FakeGeocoder()
    app = configure_test_app(monkeypatch, pool, geocoder)

    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/users/addresses/{ADDRESS_ID}",
                json={"entrance": " 3 ", "floor": None},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["entrance"] == "3"
    assert response.json()["floor"] is None
    assert geocoder.calls == []
    assert pool.fetchrow_query is not None
    assert "SET entrance = $1, floor = $2" in pool.fetchrow_query
    assert pool.fetchrow_args == ("3", None, ADDRESS_ID, USER_ID)


def test_patch_custom_label_does_not_call_yandex(monkeypatch: Any) -> None:
    pool = AddressPool()
    geocoder = FakeGeocoder()
    app = configure_test_app(monkeypatch, pool, geocoder)

    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/users/addresses/{ADDRESS_ID}",
                json={"label": "Parents"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["label"] == "Parents"
    assert geocoder.calls == []
    assert pool.fetchrow_query is not None
    assert "SET label = $1" in pool.fetchrow_query
    assert pool.fetchrow_args == ("Parents", ADDRESS_ID, USER_ID)


def test_patch_can_clear_label_without_calling_yandex(monkeypatch: Any) -> None:
    pool = AddressPool()
    geocoder = FakeGeocoder()
    app = configure_test_app(monkeypatch, pool, geocoder)

    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/users/addresses/{ADDRESS_ID}",
                json={"label": None},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["label"] is None
    assert geocoder.calls == []
    assert pool.fetchrow_query is not None
    assert "SET label = $1" in pool.fetchrow_query
    assert pool.fetchrow_args == (None, ADDRESS_ID, USER_ID)


def test_patch_location_replaces_all_map_derived_fields(monkeypatch: Any) -> None:
    new_location = AddressLocation(latitude=40.7894, longitude=43.8475)
    pool = AddressPool()
    geocoder = FakeGeocoder(
        resolved_address(
            region=ArmeniaRegion.SHIRAK,
            city="Gyumri",
            street="Gayi Street",
            building_number="1",
            formatted_address="Armenia, Shirak Province, Gyumri, Gayi Street, 1",
            latitude=new_location.latitude,
            longitude=new_location.longitude,
        )
    )
    app = configure_test_app(monkeypatch, pool, geocoder)

    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/users/addresses/{ADDRESS_ID}",
                json={"location": new_location.model_dump()},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["city"] == "Gyumri"
    assert response.json()["region"] == "Shirak"
    assert response.json()["location"] == new_location.model_dump()
    assert geocoder.calls == [new_location]
    assert pool.fetchrow_query is not None
    assert "country = $1, region = $2::armenia_region" in pool.fetchrow_query
    assert pool.fetchrow_args is not None
    assert pool.fetchrow_args[-2:] == (ADDRESS_ID, USER_ID)


def test_patch_address_as_default_replaces_previous_default(monkeypatch: Any) -> None:
    pool = AddressPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/users/addresses/{ADDRESS_ID}",
                json={"is_default": True},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["is_default"] is True
    assert pool.advisory_lock_count == 1
    assert pool.transaction_count == 1
    assert pool.cleared_default_args == (USER_ID, ADDRESS_ID)
    assert pool.fetchrow_args == (True, ADDRESS_ID, USER_ID)


def test_patch_rejects_empty_null_location_and_derived_fields(monkeypatch: Any) -> None:
    pool = AddressPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            empty_response = client.patch(f"/api/v1/users/addresses/{ADDRESS_ID}", json={})
            null_response = client.patch(
                f"/api/v1/users/addresses/{ADDRESS_ID}", json={"location": None}
            )
            derived_response = client.patch(
                f"/api/v1/users/addresses/{ADDRESS_ID}", json={"street": "Other Street"}
            )
            long_label_response = client.patch(
                f"/api/v1/users/addresses/{ADDRESS_ID}", json={"label": "x" * 33}
            )
    finally:
        app.dependency_overrides.clear()

    assert empty_response.status_code == 422
    assert null_response.status_code == 422
    assert derived_response.status_code == 422
    assert long_label_response.status_code == 422
    assert pool.fetchrow_query is None


def test_missing_address_returns_not_found_for_read_update_and_delete(monkeypatch: Any) -> None:
    pool = AddressPool(address_exists=False)
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            read_response = client.get(f"/api/v1/users/addresses/{ADDRESS_ID}")
            update_response = client.patch(
                f"/api/v1/users/addresses/{ADDRESS_ID}", json={"floor": "4"}
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


def test_addresses_and_resolver_require_authentication(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, AddressPool(), authenticated=False)

    try:
        with TestClient(app) as client:
            list_response = client.get("/api/v1/users/addresses")
            resolve_response = client.post(
                "/api/v1/users/addresses/resolve",
                json={"latitude": LATITUDE, "longitude": LONGITUDE},
            )
    finally:
        app.dependency_overrides.clear()

    assert list_response.status_code == 401
    assert resolve_response.status_code == 401
