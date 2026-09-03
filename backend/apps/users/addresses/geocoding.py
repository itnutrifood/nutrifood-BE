import logging
import math
import re
from dataclasses import dataclass
from typing import Annotated, Protocol, cast

import httpx
from fastapi import Depends, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.apps.users.addresses.enums import ArmeniaRegion, Country
from backend.apps.users.addresses.exceptions import (
    AddressGeocodingNotConfiguredError,
    AddressGeocodingUnavailableError,
    InvalidAddressLocationError,
)
from backend.apps.users.addresses.schemas import AddressLocation
from backend.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedAddress:
    country: Country
    region: ArmeniaRegion
    city: str
    street: str
    building_number: str
    formatted_address: str
    latitude: float
    longitude: float
    provider_uri: str | None
    geocode_kind: str
    geocode_precision: str | None


class AddressGeocoder(Protocol):
    async def reverse_geocode(self, location: AddressLocation) -> ResolvedAddress: ...


class _YandexAddressComponent(BaseModel):
    kind: str
    name: str


class _YandexAddress(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    country_code: str = ""
    formatted: str
    components: list[_YandexAddressComponent] = Field(alias="Components")


class _YandexGeocoderMetadata(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    kind: str
    precision: str | None = None
    address: _YandexAddress = Field(alias="Address")


class _YandexMetadataProperty(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    geocoder_metadata: _YandexGeocoderMetadata = Field(alias="GeocoderMetaData")


class _YandexPoint(BaseModel):
    pos: str


class _YandexGeoObject(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    metadata_property: _YandexMetadataProperty = Field(alias="metaDataProperty")
    point: _YandexPoint = Field(alias="Point")
    uri: str | None = None


class _YandexFeatureMember(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    geo_object: _YandexGeoObject = Field(alias="GeoObject")


class _YandexGeoObjectCollection(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    feature_members: list[_YandexFeatureMember] = Field(alias="featureMember")


class _YandexResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    collection: _YandexGeoObjectCollection = Field(alias="GeoObjectCollection")


class _YandexPayload(BaseModel):
    response: _YandexResponse


ARMENIA_COUNTRY_CODES = frozenset({"AM", "ARM"})
ARMENIA_NAMES = frozenset({"armenia", "republic of armenia", "армения", "հայաստան"})


def _normalized_name(value: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


REGION_ALIASES: dict[str, ArmeniaRegion] = {}
for _region in ArmeniaRegion:
    REGION_ALIASES[_normalized_name(_region.value)] = _region
    REGION_ALIASES[_normalized_name(f"{_region.value} Province")] = _region
    REGION_ALIASES[_normalized_name(f"{_region.value} Region")] = _region
    REGION_ALIASES[_normalized_name(f"{_region.value} Marz")] = _region

REGION_ALIASES.update(
    {
        _normalized_name(name): region
        for name, region in {
            "Арагацотнская область": ArmeniaRegion.ARAGATSOTN,
            "Араратская область": ArmeniaRegion.ARARAT,
            "Армавирская область": ArmeniaRegion.ARMAVIR,
            "Гегаркуникская область": ArmeniaRegion.GEGHARKUNIK,
            "Котайкская область": ArmeniaRegion.KOTAYK,
            "Лорийская область": ArmeniaRegion.LORI,
            "Ширакская область": ArmeniaRegion.SHIRAK,
            "Сюникская область": ArmeniaRegion.SYUNIK,
            "Тавушская область": ArmeniaRegion.TAVUSH,
            "Вайоцдзорская область": ArmeniaRegion.VAYOTS_DZOR,
            "Ереван": ArmeniaRegion.YEREVAN,
            "Yerevan Municipality": ArmeniaRegion.YEREVAN,
            "Երևան": ArmeniaRegion.YEREVAN,
        }.items()
    }
)


def _component_names(
    components: list[_YandexAddressComponent],
    kind: str,
) -> list[str]:
    return [component.name.strip() for component in components if component.kind == kind]


def _required_component(
    components: list[_YandexAddressComponent],
    kind: str,
    display_name: str,
    max_length: int,
) -> str:
    values = _component_names(components, kind)
    if not values or not values[-1]:
        raise InvalidAddressLocationError(
            f"Yandex could not determine the {display_name} for this location"
        )
    if len(values[-1]) > max_length:
        raise InvalidAddressLocationError(
            f"The {display_name} returned for this location is too long"
        )
    return values[-1]


def _resolve_region(components: list[_YandexAddressComponent]) -> ArmeniaRegion:
    candidates = _component_names(components, "province")
    candidates.extend(_component_names(components, "locality"))
    for candidate in candidates:
        region = REGION_ALIASES.get(_normalized_name(candidate))
        if region is not None:
            return region
    raise InvalidAddressLocationError("Yandex could not determine a supported Armenian region")


def _validate_country(
    country_code: str,
    components: list[_YandexAddressComponent],
) -> None:
    normalized_code = country_code.strip().upper()
    countries = {_normalized_name(value) for value in _component_names(components, "country")}
    if normalized_code not in ARMENIA_COUNTRY_CODES and countries.isdisjoint(ARMENIA_NAMES):
        raise InvalidAddressLocationError("Delivery addresses must be located in Armenia")


def _parse_point(pos: str) -> tuple[float, float]:
    try:
        longitude_text, latitude_text = pos.split()
        longitude = float(longitude_text)
        latitude = float(latitude_text)
    except (TypeError, ValueError) as exc:
        raise AddressGeocodingUnavailableError from exc
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise AddressGeocodingUnavailableError
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise AddressGeocodingUnavailableError
    return latitude, longitude


def _distance_meters(first: AddressLocation, latitude: float, longitude: float) -> float:
    earth_radius_meters = 6_371_000
    first_latitude = math.radians(first.latitude)
    second_latitude = math.radians(latitude)
    latitude_delta = second_latitude - first_latitude
    longitude_delta = math.radians(longitude - first.longitude)
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(first_latitude) * math.cos(second_latitude) * math.sin(longitude_delta / 2) ** 2
    )
    return 2 * earth_radius_meters * math.asin(math.sqrt(min(1, haversine)))


class YandexGeocoder:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        language: str,
        max_result_distance_meters: float,
        client: httpx.AsyncClient,
    ) -> None:
        self._api_key = api_key.strip()
        self._base_url = base_url
        self._language = language
        self._max_result_distance_meters = max_result_distance_meters
        self._client = client

    async def close(self) -> None:
        await self._client.aclose()

    async def reverse_geocode(self, location: AddressLocation) -> ResolvedAddress:
        if not self._api_key:
            raise AddressGeocodingNotConfiguredError

        try:
            response = await self._client.get(
                self._base_url,
                params={
                    "apikey": self._api_key,
                    "geocode": f"{location.longitude},{location.latitude}",
                    "lang": self._language,
                    "kind": "house",
                    "results": 1,
                    "format": "json",
                },
            )
        except httpx.RequestError as exc:
            logger.warning("Yandex Geocoder request failed: %s", type(exc).__name__)
            raise AddressGeocodingUnavailableError from exc

        if response.status_code == 429:
            logger.warning("Yandex Geocoder rate limit was exceeded")
            raise AddressGeocodingUnavailableError
        if response.is_error:
            logger.error("Yandex Geocoder returned HTTP %d", response.status_code)
            raise AddressGeocodingUnavailableError

        try:
            payload = _YandexPayload.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            logger.error("Yandex Geocoder returned an invalid response")
            raise AddressGeocodingUnavailableError from exc

        if not payload.response.collection.feature_members:
            raise InvalidAddressLocationError("No delivery address was found at this location")

        geo_object = payload.response.collection.feature_members[0].geo_object
        metadata = geo_object.metadata_property.geocoder_metadata
        components = metadata.address.components

        if metadata.kind != "house":
            raise InvalidAddressLocationError(
                "Select a building so Yandex can determine an exact delivery address"
            )

        _validate_country(metadata.address.country_code, components)
        city = _required_component(components, "locality", "city or locality", 150)
        street = _required_component(components, "street", "street", 255)
        building_number = _required_component(components, "house", "building number", 50)
        region = _resolve_region(components)
        result_latitude, result_longitude = _parse_point(geo_object.point.pos)
        if (
            _distance_meters(location, result_latitude, result_longitude)
            > self._max_result_distance_meters
        ):
            raise InvalidAddressLocationError(
                "The selected point is too far from the nearest recognized building"
            )

        formatted_address = metadata.address.formatted.strip()
        if not formatted_address or len(formatted_address) > 500:
            raise AddressGeocodingUnavailableError

        provider_uri = (geo_object.uri or "").strip() or None
        if provider_uri is not None and len(provider_uri) > 512:
            provider_uri = None
        geocode_precision = (metadata.precision or "").strip() or None
        if geocode_precision is not None and len(geocode_precision) > 32:
            raise AddressGeocodingUnavailableError

        return ResolvedAddress(
            country=Country.ARMENIA,
            region=region,
            city=city,
            street=street,
            building_number=building_number,
            formatted_address=formatted_address,
            latitude=location.latitude,
            longitude=location.longitude,
            provider_uri=provider_uri,
            geocode_kind=metadata.kind,
            geocode_precision=geocode_precision,
        )


def create_yandex_geocoder(settings: Settings | None = None) -> YandexGeocoder:
    resolved_settings = settings or get_settings()
    client = httpx.AsyncClient(
        timeout=resolved_settings.yandex_geocoder_timeout_seconds,
        headers={"User-Agent": f"{resolved_settings.app_name}/address-geocoder"},
    )
    return YandexGeocoder(
        api_key=resolved_settings.yandex_geocoder_api_key,
        base_url=resolved_settings.yandex_geocoder_base_url,
        language=resolved_settings.yandex_geocoder_language,
        max_result_distance_meters=resolved_settings.yandex_geocoder_max_distance_meters,
        client=client,
    )


def get_address_geocoder(request: Request) -> AddressGeocoder:
    return cast(AddressGeocoder, request.app.state.address_geocoder)


AddressGeocoderDependency = Annotated[AddressGeocoder, Depends(get_address_geocoder)]
