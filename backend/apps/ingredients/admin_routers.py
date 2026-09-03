from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response
from fastapi import status as http_status

from backend.apps.ingredients.admin_service import (
    create_ingredient,
    delete_ingredient,
    get_ingredient,
    list_ingredients,
    update_ingredient,
)
from backend.apps.ingredients.schemas import (
    IngredientCreate,
    IngredientListResponse,
    IngredientRead,
    IngredientUpdate,
)
from backend.config.database import DbPool

router = APIRouter(prefix="/ingredients", tags=["admin:ingredients"])


@router.post("", response_model=IngredientRead, status_code=http_status.HTTP_201_CREATED)
async def create_admin_ingredient(
    payload: IngredientCreate,
    pool: DbPool,
) -> IngredientRead:
    return await create_ingredient(pool, payload)


@router.get("", response_model=IngredientListResponse)
async def list_admin_ingredients(
    pool: DbPool,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> IngredientListResponse:
    return await list_ingredients(pool, page, limit)


@router.get("/{ingredient_id}", response_model=IngredientRead)
async def read_admin_ingredient(ingredient_id: UUID, pool: DbPool) -> IngredientRead:
    return await get_ingredient(pool, ingredient_id)


@router.patch("/{ingredient_id}", response_model=IngredientRead)
async def update_admin_ingredient(
    ingredient_id: UUID,
    payload: IngredientUpdate,
    pool: DbPool,
) -> IngredientRead:
    return await update_ingredient(pool, ingredient_id, payload)


@router.delete("/{ingredient_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_admin_ingredient(ingredient_id: UUID, pool: DbPool) -> Response:
    await delete_ingredient(pool, ingredient_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
