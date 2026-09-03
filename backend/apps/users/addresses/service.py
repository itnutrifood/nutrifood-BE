from uuid import UUID

import asyncpg

from backend.apps.users.addresses import repository
from backend.apps.users.addresses.geocoding import AddressGeocoder, ResolvedAddress
from backend.apps.users.addresses.schemas import (
    AddressCreate,
    AddressLocation,
    AddressRead,
    AddressResolutionRead,
    AddressUpdate,
)


def _resolution_read(resolved: ResolvedAddress) -> AddressResolutionRead:
    return AddressResolutionRead(
        country=resolved.country,
        region=resolved.region,
        city=resolved.city,
        street=resolved.street,
        building_number=resolved.building_number,
        formatted_address=resolved.formatted_address,
        location=AddressLocation(
            latitude=resolved.latitude,
            longitude=resolved.longitude,
        ),
        geocode_precision=resolved.geocode_precision,
    )


async def resolve_address(
    geocoder: AddressGeocoder,
    location: AddressLocation,
) -> AddressResolutionRead:
    return _resolution_read(await geocoder.reverse_geocode(location))


async def create_address(
    pool: asyncpg.Pool,
    geocoder: AddressGeocoder,
    user_id: UUID,
    payload: AddressCreate,
) -> AddressRead:
    resolved = await geocoder.reverse_geocode(payload.location)
    return await repository.create_address(pool, user_id, payload, resolved)


async def list_addresses(pool: asyncpg.Pool, user_id: UUID) -> list[AddressRead]:
    return await repository.list_addresses(pool, user_id)


async def get_address(
    pool: asyncpg.Pool,
    user_id: UUID,
    address_id: UUID,
) -> AddressRead:
    return await repository.get_address(pool, user_id, address_id)


async def update_address(
    pool: asyncpg.Pool,
    geocoder: AddressGeocoder,
    user_id: UUID,
    address_id: UUID,
    payload: AddressUpdate,
) -> AddressRead:
    if payload.location is not None:
        # Do not spend a billable geocoding request for an address the caller does not own.
        await repository.get_address(pool, user_id, address_id)
    resolved = (
        await geocoder.reverse_geocode(payload.location) if payload.location is not None else None
    )
    return await repository.update_address(pool, user_id, address_id, payload, resolved)


async def delete_address(
    pool: asyncpg.Pool,
    user_id: UUID,
    address_id: UUID,
) -> None:
    await repository.delete_address(pool, user_id, address_id)
