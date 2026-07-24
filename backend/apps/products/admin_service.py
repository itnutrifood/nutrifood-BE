from collections.abc import Sequence
from uuid import UUID

import asyncpg

from backend.apps.products import repository
from backend.apps.products.exceptions import ProductCategoryNotFoundError
from backend.apps.products.schemas import (
    ProductCreate,
    ProductListResponse,
    ProductRead,
    ProductUpdate,
)


async def _ensure_categories_exist(
    pool: asyncpg.Pool,
    category_ids: Sequence[UUID],
) -> None:
    if not await repository.categories_exist(pool, category_ids):
        raise ProductCategoryNotFoundError


async def create_product(pool: asyncpg.Pool, payload: ProductCreate) -> ProductRead:
    await _ensure_categories_exist(pool, payload.category_ids)
    return await repository.create_product(pool, payload)


async def get_product(pool: asyncpg.Pool, product_id: UUID) -> ProductRead:
    return await repository.get_product(pool, product_id)


async def list_products(
    pool: asyncpg.Pool,
    category_id: UUID | None,
    page: int,
    limit: int,
) -> ProductListResponse:
    return await repository.list_products(pool, category_id, page, limit)


async def update_product(
    pool: asyncpg.Pool,
    product_id: UUID,
    payload: ProductUpdate,
) -> ProductRead:
    if "category_ids" in payload.model_fields_set:
        await _ensure_categories_exist(pool, payload.category_ids or [])
    return await repository.update_product(pool, product_id, payload)


async def delete_product(pool: asyncpg.Pool, product_id: UUID) -> None:
    await repository.delete_product(pool, product_id)
