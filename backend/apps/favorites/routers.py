from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response
from fastapi import status as http_status

from backend.apps.accounts.dependencies import RequireAuth
from backend.apps.common.localization import LocaleFromPath
from backend.apps.common.pagination import CursorPage
from backend.apps.favorites.schemas import FavoriteProductsAdd
from backend.apps.favorites.service import (
    add_favorite_product,
    add_favorite_products,
    list_favorite_products,
    remove_favorite_product,
)
from backend.apps.products.schemas import PublicProductRead
from backend.config.database import DbPool

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.get("", response_model=CursorPage[PublicProductRead])
async def list_user_favorites(
    language: LocaleFromPath,
    current_user: RequireAuth,
    pool: DbPool,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> CursorPage[PublicProductRead]:
    return await list_favorite_products(
        pool=pool,
        user_id=current_user.id,
        language=language,
        limit=limit,
        cursor=cursor,
    )


@router.put("/{product_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def add_user_favorite(
    product_id: UUID,
    current_user: RequireAuth,
    pool: DbPool,
) -> Response:
    await add_favorite_product(pool, current_user.id, product_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@router.put("", status_code=http_status.HTTP_204_NO_CONTENT)
async def add_user_favorites(
    payload: FavoriteProductsAdd,
    current_user: RequireAuth,
    pool: DbPool,
) -> Response:
    await add_favorite_products(pool, current_user.id, payload.product_ids)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@router.delete("/{product_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def remove_user_favorite(
    product_id: UUID,
    current_user: RequireAuth,
    pool: DbPool,
) -> Response:
    await remove_favorite_product(pool, current_user.id, product_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
