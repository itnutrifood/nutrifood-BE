from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import asyncpg

from backend.apps.common.db import rows_affected
from backend.apps.users.addresses.enums import ArmeniaRegion, Country
from backend.apps.users.addresses.exceptions import AddressNotFoundError
from backend.apps.users.addresses.schemas import AddressCreate, AddressRead, AddressUpdate

ADDRESS_COLUMNS = """
    id,
    country,
    region::text AS region,
    city,
    street,
    building_number,
    entrance,
    floor,
    is_default,
    created_at,
    updated_at
"""


def address_from_record(record: Mapping[str, object]) -> AddressRead:
    return AddressRead(
        id=cast(UUID, record["id"]),
        country=Country(cast(str, record["country"])),
        region=ArmeniaRegion(cast(str, record["region"])),
        city=cast(str, record["city"]),
        street=cast(str, record["street"]),
        building_number=cast(str, record["building_number"]),
        entrance=cast(str | None, record["entrance"]),
        floor=cast(str | None, record["floor"]),
        is_default=cast(bool, record["is_default"]),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


async def _insert_address(
    connection: asyncpg.Connection | asyncpg.Pool,
    user_id: UUID,
    payload: AddressCreate,
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
                is_default
            )
            VALUES ($1, $2, $3::armenia_region, $4, $5, $6, $7, $8, $9)
            RETURNING {ADDRESS_COLUMNS}
            """,
            user_id,
            payload.country.value,
            payload.region.value,
            payload.city,
            payload.street,
            payload.building_number,
            payload.entrance,
            payload.floor,
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
        user_id,
    )


async def create_address(
    pool: asyncpg.Pool,
    user_id: UUID,
    payload: AddressCreate,
) -> AddressRead:
    if not payload.is_default:
        return await _insert_address(pool, user_id, payload)

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
        return await _insert_address(connection, user_id, payload)


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
) -> AddressRead:
    assignments: list[str] = []
    params: list[Any] = []

    if "country" in payload.model_fields_set:
        params.append(cast(Country, payload.country).value)
        assignments.append(f"country = ${len(params)}")
    if "region" in payload.model_fields_set:
        params.append(cast(ArmeniaRegion, payload.region).value)
        assignments.append(f"region = ${len(params)}::armenia_region")
    for field_name in ("city", "street", "building_number", "entrance", "floor"):
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
) -> AddressRead:
    if payload.is_default is not True:
        return await _update_address(pool, user_id, address_id, payload)

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
        return await _update_address(connection, user_id, address_id, payload)


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
