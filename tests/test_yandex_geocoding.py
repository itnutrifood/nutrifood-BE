from collections.abc import Awaitable, Callable

import httpx
import pytest
from backend.apps.users.addresses.enums import ArmeniaRegion
from backend.apps.users.addresses.exceptions import (
    AddressGeocodingNotConfiguredError,
    AddressGeocodingUnavailableError,
    InvalidAddressLocationError,
)
from backend.apps.users.addresses.geocoding import YandexGeocoder
from backend.apps.users.addresses.schemas import AddressLocation

LATITUDE = 40.1811
LONGITUDE = 44.5136
LOCATION = AddressLocation(latitude=LATITUDE, longitude=LONGITUDE)
Handler = Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]


def yandex_response(
    *,
    country_code: str = "AM",
    country: str = "Armenia",
    province: str = "Yerevan",
    locality: str = "Yerevan",
    street: str | None = "Northern Avenue",
    house: str | None = "10/1",
    kind: str = "house",
    point: str = "44.5136 40.1811",
) -> dict[str, object]:
    components = [
        {"kind": "country", "name": country},
        {"kind": "province", "name": province},
        {"kind": "locality", "name": locality},
    ]
    if street is not None:
        components.append({"kind": "street", "name": street})
    if house is not None:
        components.append({"kind": "house", "name": house})
    return {
        "response": {
            "GeoObjectCollection": {
                "featureMember": [
                    {
                        "GeoObject": {
                            "metaDataProperty": {
                                "GeocoderMetaData": {
                                    "kind": kind,
                                    "precision": "exact",
                                    "Address": {
                                        "country_code": country_code,
                                        "formatted": ("Armenia, Yerevan, Northern Avenue, 10/1"),
                                        "Components": components,
                                    },
                                }
                            },
                            "Point": {"pos": point},
                            "uri": "ymapsbm1://geo?data=test",
                        }
                    }
                ]
            }
        }
    }


def geocoder(
    handler: Handler,
    *,
    api_key: str = "test-yandex-key",
    max_distance: float = 250,
) -> YandexGeocoder:
    return YandexGeocoder(
        api_key=api_key,
        base_url="https://geocode-maps.yandex.ru/v1/",
        language="en_RU",
        max_result_distance_meters=max_distance,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def test_reverse_geocode_sends_longitude_first_and_parses_address() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json=yandex_response())

    service = geocoder(handler)
    try:
        result = await service.reverse_geocode(LOCATION)
    finally:
        await service.close()

    assert captured_request is not None
    assert captured_request.url.params["geocode"] == f"{LONGITUDE},{LATITUDE}"
    assert captured_request.url.params["kind"] == "house"
    assert captured_request.url.params["results"] == "1"
    assert captured_request.url.params["format"] == "json"
    assert captured_request.url.params["lang"] == "en_RU"
    assert result.region is ArmeniaRegion.YEREVAN
    assert result.city == "Yerevan"
    assert result.street == "Northern Avenue"
    assert result.building_number == "10/1"
    assert result.latitude == LATITUDE
    assert result.longitude == LONGITUDE
    assert result.provider_uri == "ymapsbm1://geo?data=test"


async def test_reverse_geocode_normalizes_english_and_russian_region_names() -> None:
    responses = iter(
        [
            yandex_response(province="Shirak Province", locality="Gyumri"),
            yandex_response(province="Котайкская область", locality="Цахкадзор"),
        ]
    )
    service = geocoder(lambda _request: httpx.Response(200, json=next(responses)))
    try:
        shirak = await service.reverse_geocode(LOCATION)
        kotayk = await service.reverse_geocode(LOCATION)
    finally:
        await service.close()

    assert shirak.region is ArmeniaRegion.SHIRAK
    assert kotayk.region is ArmeniaRegion.KOTAYK


async def test_reverse_geocode_accepts_armenia_component_when_code_is_missing() -> None:
    service = geocoder(lambda _request: httpx.Response(200, json=yandex_response(country_code="")))
    try:
        result = await service.reverse_geocode(LOCATION)
    finally:
        await service.close()

    assert result.region is ArmeniaRegion.YEREVAN


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        (
            {
                "response": {"GeoObjectCollection": {"featureMember": []}},
            },
            "No delivery address was found at this location",
        ),
        (
            yandex_response(kind="street"),
            "Select a building so Yandex can determine an exact delivery address",
        ),
        (
            yandex_response(country_code="GE", country="Georgia"),
            "Delivery addresses must be located in Armenia",
        ),
        (
            yandex_response(street=None),
            "Yandex could not determine the street for this location",
        ),
        (
            yandex_response(province="Unsupported Province", locality="Unknown"),
            "Yandex could not determine a supported Armenian region",
        ),
    ],
)
async def test_reverse_geocode_rejects_unusable_locations(
    payload: dict[str, object],
    detail: str,
) -> None:
    service = geocoder(lambda _request: httpx.Response(200, json=payload))
    try:
        with pytest.raises(InvalidAddressLocationError, match=detail):
            await service.reverse_geocode(LOCATION)
    finally:
        await service.close()


async def test_reverse_geocode_rejects_a_house_too_far_from_selected_pin() -> None:
    service = geocoder(
        lambda _request: httpx.Response(
            200,
            json=yandex_response(point="44.6000 40.2500"),
        ),
        max_distance=100,
    )
    try:
        with pytest.raises(InvalidAddressLocationError, match="too far"):
            await service.reverse_geocode(LOCATION)
    finally:
        await service.close()


async def test_reverse_geocode_requires_configuration() -> None:
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json=yandex_response())

    service = geocoder(handler, api_key=" ")
    try:
        with pytest.raises(AddressGeocodingNotConfiguredError):
            await service.reverse_geocode(LOCATION)
    finally:
        await service.close()

    assert called is False


@pytest.mark.parametrize("status_code", [400, 403, 429, 500])
async def test_reverse_geocode_maps_http_errors_to_unavailable(status_code: int) -> None:
    service = geocoder(lambda _request: httpx.Response(status_code, json={"message": "error"}))
    try:
        with pytest.raises(AddressGeocodingUnavailableError):
            await service.reverse_geocode(LOCATION)
    finally:
        await service.close()


async def test_reverse_geocode_maps_network_and_malformed_responses_to_unavailable() -> None:
    def network_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    service = geocoder(network_error)
    try:
        with pytest.raises(AddressGeocodingUnavailableError):
            await service.reverse_geocode(LOCATION)
    finally:
        await service.close()

    service = geocoder(lambda _request: httpx.Response(200, content=b"not-json"))
    try:
        with pytest.raises(AddressGeocodingUnavailableError):
            await service.reverse_geocode(LOCATION)
    finally:
        await service.close()
