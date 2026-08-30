from uuid import UUID

import asyncpg

from backend.apps.categories import repository
from backend.apps.categories.exceptions import (
    CategoryFilterConflictError,
    CategoryHierarchyError,
    CategoryNotFoundError,
    ParentCategoryNotFoundError,
)
from backend.apps.categories.schemas import (
    CategoryCreate,
    CategoryListResponse,
    CategoryRead,
    CategoryUpdate,
)
from backend.apps.common.enums import CategoryStatus

type CategoryDatabase = asyncpg.Connection | asyncpg.Pool


async def _ensure_parent_exists(pool: CategoryDatabase, parent_id: UUID) -> None:
    if not await repository.category_exists(pool, parent_id):
        raise ParentCategoryNotFoundError


async def _validate_parent_for_update(
    pool: CategoryDatabase,
    category_id: UUID,
    parent_id: UUID | None,
) -> None:
    if parent_id is None:
        return
    if parent_id == category_id:
        raise CategoryHierarchyError("A category cannot be its own parent")

    await _ensure_parent_exists(pool, parent_id)
    if await repository.is_descendant(pool, category_id, parent_id):
        raise CategoryHierarchyError("A category cannot be moved below one of its descendants")


async def create_category(pool: asyncpg.Pool, payload: CategoryCreate) -> CategoryRead:
    if payload.parent_id is not None:
        await _ensure_parent_exists(pool, payload.parent_id)
    return await repository.create_category(pool, payload)


async def get_category(pool: asyncpg.Pool, category_id: UUID) -> CategoryRead:
    return await repository.get_category(pool, category_id)


async def list_categories(
    pool: asyncpg.Pool,
    status_filter: CategoryStatus | None,
    parent_id: UUID | None,
    root_only: bool,
    page: int,
    limit: int,
) -> CategoryListResponse:
    if root_only and parent_id is not None:
        raise CategoryFilterConflictError("root_only and parent_id cannot be used together")
    return await repository.list_categories(
        pool,
        status_filter,
        parent_id,
        root_only,
        page,
        limit,
    )


async def update_category(
    pool: asyncpg.Pool,
    category_id: UUID,
    payload: CategoryUpdate,
) -> CategoryRead:
    if "parent_id" not in payload.model_fields_set:
        if not await repository.category_exists(pool, category_id):
            raise CategoryNotFoundError
        return await repository.update_category(pool, category_id, payload)

    async with pool.acquire() as connection, connection.transaction():
        await repository.lock_category_hierarchy(connection)

        # Re-read all hierarchy state after acquiring the transaction-scoped lock. A
        # concurrent parent move may have committed while this request was waiting.
        if not await repository.category_exists(connection, category_id):
            raise CategoryNotFoundError
        await _validate_parent_for_update(connection, category_id, payload.parent_id)
        return await repository.update_category(connection, category_id, payload)


async def delete_category(pool: asyncpg.Pool, category_id: UUID) -> None:
    await repository.delete_category(pool, category_id)
