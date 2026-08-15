from uuid import UUID

import asyncpg

from backend.apps.users.addresses import repository
from backend.apps.users.addresses.schemas import AddressCreate, AddressRead, AddressUpdate


async def create_address(
    pool: asyncpg.Pool,
    user_id: UUID,
    payload: AddressCreate,
) -> AddressRead:
    return await repository.create_address(pool, user_id, payload)


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
    user_id: UUID,
    address_id: UUID,
    payload: AddressUpdate,
) -> AddressRead:
    return await repository.update_address(pool, user_id, address_id, payload)


async def delete_address(
    pool: asyncpg.Pool,
    user_id: UUID,
    address_id: UUID,
) -> None:
    await repository.delete_address(pool, user_id, address_id)
