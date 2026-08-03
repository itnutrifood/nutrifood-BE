from collections.abc import Sequence
from uuid import UUID

import asyncpg

from backend.apps.assets.service import delete_product_image_urls
from backend.apps.assets.storage import AssetObjectStorage
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
    storage: AssetObjectStorage,
) -> ProductRead:
    if "category_ids" in payload.model_fields_set:
        await _ensure_categories_exist(pool, payload.category_ids or [])

    previous_image_urls: set[str] = set()
    if "images" in payload.model_fields_set:
        product = await repository.get_product(pool, product_id)
        previous_image_urls = {image.url for image in product.images}

    updated_product = await repository.update_product(pool, product_id, payload)
    if "images" in payload.model_fields_set:
        current_image_urls = {image.url for image in updated_product.images}
        await delete_product_image_urls(storage, previous_image_urls - current_image_urls)
    return updated_product


async def delete_product(
    pool: asyncpg.Pool,
    product_id: UUID,
    storage: AssetObjectStorage,
) -> None:
    product = await repository.get_product(pool, product_id)
    await repository.delete_product(pool, product_id)
    await delete_product_image_urls(storage, (image.url for image in product.images))
