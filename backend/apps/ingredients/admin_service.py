from uuid import UUID

import asyncpg

from backend.apps.ingredients import repository
from backend.apps.ingredients.schemas import (
    IngredientCreate,
    IngredientListResponse,
    IngredientRead,
    IngredientUpdate,
)


async def create_ingredient(pool: asyncpg.Pool, payload: IngredientCreate) -> IngredientRead:
    return await repository.create_ingredient(pool, payload)


async def get_ingredient(pool: asyncpg.Pool, ingredient_id: UUID) -> IngredientRead:
    return await repository.get_ingredient(pool, ingredient_id)


async def list_ingredients(
    pool: asyncpg.Pool,
    page: int,
    limit: int,
) -> IngredientListResponse:
    return await repository.list_ingredients(pool, page, limit)


async def update_ingredient(
    pool: asyncpg.Pool,
    ingredient_id: UUID,
    payload: IngredientUpdate,
) -> IngredientRead:
    return await repository.update_ingredient(pool, ingredient_id, payload)


async def delete_ingredient(pool: asyncpg.Pool, ingredient_id: UUID) -> None:
    await repository.delete_ingredient(pool, ingredient_id)
