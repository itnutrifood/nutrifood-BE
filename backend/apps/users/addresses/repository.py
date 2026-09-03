from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import asyncpg

from backend.apps.common.db import rows_affected
from backend.apps.users.addresses.enums import (
    AddressLocationSource,
    ArmeniaRegion,
    Country,
)
from backend.apps.users.addresses.exceptions import AddressNotFoundError
from backend.apps.users.addresses.geocoding import ResolvedAddress
from backend.apps.users.addresses.schemas import (
    AddressCreate,
    AddressLocation,
    AddressRead,
    AddressUpdate,
)

ADDRESS_COLUMNS = """
    id,
    label,
    country,
    region::text AS region,
    city,
    street,
    building_number,
    entrance,
    floor,
    apartment,
    latitude,
    longitude,
    formatted_address,
    location_source,
    provider_uri,
    geocode_kind,
    geocode_precision,
    is_default,
    created_at,
    updated_at
"""


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(cast(Decimal | float, value))


def address_from_record(record: Mapping[str, object]) -> AddressRead:
    latitude = _optional_float(record["latitude"])
    longitude = _optional_float(record["longitude"])
    return AddressRead(
        id=cast(UUID, record["id"]),
        label=cast(str | None, record["label"]),
        country=Country(cast(str, record["country"])),
        region=ArmeniaRegion(cast(str, record["region"])),
        city=cast(str, record["city"]),
        street=cast(str, record["street"]),
        building_number=cast(str, record["building_number"]),
        entrance=cast(str | None, record["entrance"]),
        floor=cast(str | None, record["floor"]),
        apartment=cast(str | None, record["apartment"]),
        formatted_address=cast(str | None, record["formatted_address"]),
        location=(
            AddressLocation(latitude=latitude, longitude=longitude)
            if latitude is not None and longitude is not None
            else None
        ),
        location_source=AddressLocationSource(cast(str, record["location_source"])),
        geocode_precision=cast(str | None, record["geocode_precision"]),
        is_default=cast(bool, record["is_default"]),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


async def _insert_address(
    connection: asyncpg.Connection | asyncpg.Pool,
    user_id: UUID,
    payload: AddressCreate,
    resolved: ResolvedAddress,
) -> AddressRead:
    row = cast(
        Mapping[str, object] | None,
        await connection.fetchrow(
            f"""
            INSERT INTO user_addresses (
                user_id,
                country,
                region,
                city,
                street,
                building_number,
                entrance,
                floor,
                apartment,
                latitude,
                longitude,
                formatted_address,
                location_source,
                provider_uri,
                geocode_kind,
                geocode_precision,
                label,
                is_default
            )
            VALUES (
                $1, $2, $3::armenia_region, $4, $5, $6, $7, $8, $9, $10, $11,
                $12, $13, $14, $15, $16, $17, $18
            )
            RETURNING {ADDRESS_COLUMNS}
            """,
            user_id,
            resolved.country.value,
            resolved.region.value,
            resolved.city,
            resolved.street,
            resolved.building_number,
            payload.entrance,
            payload.floor,
            payload.apartment,
            Decimal(str(resolved.latitude)),
            Decimal(str(resolved.longitude)),
            resolved.formatted_address,
            AddressLocationSource.YANDEX.value,
            resolved.provider_uri,
            resolved.geocode_kind,
            resolved.geocode_precision,
            payload.label,
            payload.is_default,
        ),
    )
    if row is None:
        raise RuntimeError("Address insert did not return a row")
    return address_from_record(row)


async def _lock_default_address_changes(
    connection: asyncpg.Connection,
    user_id: UUID,
) -> None:
    await connection.fetchval(
        "SELECT pg_advisory_xact_lock(hashtextextended($1::text, 0))",
        str(user_id),
    )


async def create_address(
    pool: asyncpg.Pool,
    user_id: UUID,
    payload: AddressCreate,
    resolved: ResolvedAddress,
) -> AddressRead:
    if not payload.is_default:
        return await _insert_address(pool, user_id, payload, resolved)

    async with pool.acquire() as connection, connection.transaction():
        await _lock_default_address_changes(connection, user_id)
        await connection.execute(
            """
            UPDATE user_addresses
            SET is_default = FALSE
            WHERE user_id = $1 AND is_default
            """,
            user_id,
        )
        return await _insert_address(connection, user_id, payload, resolved)


async def list_addresses(pool: asyncpg.Pool, user_id: UUID) -> list[AddressRead]:
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {ADDRESS_COLUMNS}
            FROM user_addresses
            WHERE user_id = $1
            ORDER BY created_at DESC, id DESC
            """,
            user_id,
        ),
    )
    return [address_from_record(row) for row in rows]


async def get_address(
    pool: asyncpg.Pool,
    user_id: UUID,
    address_id: UUID,
) -> AddressRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {ADDRESS_COLUMNS}
            FROM user_addresses
            WHERE id = $1 AND user_id = $2
            """,
            address_id,
            user_id,
        ),
    )
    if row is None:
        raise AddressNotFoundError
    return address_from_record(row)


async def _update_address(
    connection: asyncpg.Connection | asyncpg.Pool,
    user_id: UUID,
    address_id: UUID,
    payload: AddressUpdate,
    resolved: ResolvedAddress | None,
) -> AddressRead:
    assignments: list[str] = []
    params: list[Any] = []

    if resolved is not None:
        location_values: tuple[tuple[str, object], ...] = (
            ("country", resolved.country.value),
            ("region", resolved.region.value),
            ("city", resolved.city),
            ("street", resolved.street),
            ("building_number", resolved.building_number),
            ("latitude", Decimal(str(resolved.latitude))),
            ("longitude", Decimal(str(resolved.longitude))),
            ("formatted_address", resolved.formatted_address),
            ("location_source", AddressLocationSource.YANDEX.value),
            ("provider_uri", resolved.provider_uri),
            ("geocode_kind", resolved.geocode_kind),
            ("geocode_precision", resolved.geocode_precision),
        )
        for field_name, value in location_values:
            params.append(value)
            cast_suffix = "::armenia_region" if field_name == "region" else ""
            assignments.append(f"{field_name} = ${len(params)}{cast_suffix}")

    if "label" in payload.model_fields_set:
        params.append(payload.label)
        assignments.append(f"label = ${len(params)}")

    for field_name in ("entrance", "floor", "apartment"):
        if field_name in payload.model_fields_set:
            params.append(getattr(payload, field_name))
            assignments.append(f"{field_name} = ${len(params)}")
    if "is_default" in payload.model_fields_set:
        params.append(cast(bool, payload.is_default))
        assignments.append(f"is_default = ${len(params)}")

    params.extend([address_id, user_id])
    row = cast(
        Mapping[str, object] | None,
        await connection.fetchrow(
            f"""
            UPDATE user_addresses
            SET {", ".join(assignments)}
            WHERE id = ${len(params) - 1} AND user_id = ${len(params)}
            RETURNING {ADDRESS_COLUMNS}
            """,
            *params,
        ),
    )
    if row is None:
        raise AddressNotFoundError
    return address_from_record(row)


async def update_address(
    pool: asyncpg.Pool,
    user_id: UUID,
    address_id: UUID,
    payload: AddressUpdate,
    resolved: ResolvedAddress | None,
) -> AddressRead:
    if payload.is_default is not True:
        return await _update_address(pool, user_id, address_id, payload, resolved)

    async with pool.acquire() as connection, connection.transaction():
        await _lock_default_address_changes(connection, user_id)
        await connection.execute(
            """
            UPDATE user_addresses
            SET is_default = FALSE
            WHERE user_id = $1 AND id <> $2 AND is_default
            """,
            user_id,
            address_id,
        )
        return await _update_address(connection, user_id, address_id, payload, resolved)


async def delete_address(
    pool: asyncpg.Pool,
    user_id: UUID,
    address_id: UUID,
) -> None:
    command_status = cast(
        str,
        await pool.execute(
            "DELETE FROM user_addresses WHERE id = $1 AND user_id = $2",
            address_id,
            user_id,
        ),
    )
    if rows_affected(command_status) == 0:
        raise AddressNotFoundError
