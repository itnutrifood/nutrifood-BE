from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import status as http_status
from pydantic import BaseModel, Field

from backend.apps.accounts.auth import RequireAuth
from backend.apps.common.localization import LocaleFromPath
from backend.apps.common.pagination import CursorPage, InvalidCursorError
from backend.apps.favorites.service import (
    FavoriteProductNotFoundError,
    add_favorite_product,
    add_favorite_products,
    list_favorite_products,
    remove_favorite_product,
)
from backend.apps.products.schemas import PublicProductRead
from backend.config.database import get_pool

DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]

router = APIRouter(prefix="/favorites", tags=["favorites"])


class FavoriteProductsAdd(BaseModel):
    product_ids: list[UUID] = Field(min_length=1, max_length=100)


def _product_not_found_error(exc: FavoriteProductNotFoundError) -> HTTPException:
    return HTTPException(
        status_code=http_status.HTTP_404_NOT_FOUND,
        detail={
            "message": "One or more products were not found",
            "product_ids": [str(product_id) for product_id in exc.product_ids],
        },
    )


@router.get("", response_model=CursorPage[PublicProductRead])
async def list_user_favorites(
    language: LocaleFromPath,
    current_user: RequireAuth,
    pool: DbPool,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> CursorPage[PublicProductRead]:
    try:
        return await list_favorite_products(
            pool=pool,
            user_id=current_user.id,
            language=language,
            limit=limit,
            cursor=cursor,
        )
    except InvalidCursorError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid cursor",
        ) from exc


@router.put("/{product_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def add_user_favorite(
    product_id: UUID,
    current_user: RequireAuth,
    pool: DbPool,
) -> Response:
    try:
        await add_favorite_product(pool, current_user.id, product_id)
    except FavoriteProductNotFoundError as exc:
        raise _product_not_found_error(exc) from exc
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@router.put("", status_code=http_status.HTTP_204_NO_CONTENT)
async def add_user_favorites(
    payload: FavoriteProductsAdd,
    current_user: RequireAuth,
    pool: DbPool,
) -> Response:
    try:
        await add_favorite_products(pool, current_user.id, payload.product_ids)
    except FavoriteProductNotFoundError as exc:
        raise _product_not_found_error(exc) from exc
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@router.delete("/{product_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def remove_user_favorite(
    product_id: UUID,
    current_user: RequireAuth,
    pool: DbPool,
) -> Response:
    await remove_favorite_product(pool, current_user.id, product_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
