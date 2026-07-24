from uuid import UUID

import asyncpg

from backend.apps.common.enums import EmploymentType, OpenPositionStatus
from backend.apps.open_positions import repository
from backend.apps.open_positions.schemas import (
    OpenPositionCreate,
    OpenPositionListResponse,
    OpenPositionRead,
    OpenPositionUpdate,
)


async def create_open_position(
    pool: asyncpg.Pool,
    payload: OpenPositionCreate,
) -> OpenPositionRead:
    return await repository.create_open_position(pool, payload)


async def get_open_position(pool: asyncpg.Pool, open_position_id: UUID) -> OpenPositionRead:
    return await repository.get_open_position(pool, open_position_id)


async def list_open_positions(
    pool: asyncpg.Pool,
    status_filter: OpenPositionStatus | None,
    employment_type_filter: EmploymentType | None,
    page: int,
    limit: int,
) -> OpenPositionListResponse:
    return await repository.list_open_positions(
        pool,
        status_filter,
        employment_type_filter,
        page,
        limit,
    )


async def update_open_position(
    pool: asyncpg.Pool,
    open_position_id: UUID,
    payload: OpenPositionUpdate,
) -> OpenPositionRead:
    return await repository.update_open_position(pool, open_position_id, payload)


async def delete_open_position(pool: asyncpg.Pool, open_position_id: UUID) -> None:
    await repository.delete_open_position(pool, open_position_id)
