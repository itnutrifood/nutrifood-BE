from uuid import UUID

from fastapi import APIRouter, Response
from fastapi import status as http_status

from backend.apps.accounts.dependencies import RequireAuth
from backend.apps.cart.schemas import CartItemsUpsert, CartItemUpsert, CartRead
from backend.apps.cart.service import (
    clear_cart,
    get_cart,
    remove_cart_item,
    upsert_cart_item,
    upsert_cart_items,
)
from backend.apps.common.localization import LocaleFromPath
from backend.config.database import DbPool

router = APIRouter(prefix="/cart", tags=["cart"])


@router.get("", response_model=CartRead)
async def read_cart(
    language: LocaleFromPath,
    current_user: RequireAuth,
    pool: DbPool,
) -> CartRead:
    return await get_cart(pool, current_user.id, language)


@router.put("/{product_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def set_cart_item(
    product_id: UUID,
    payload: CartItemUpsert,
    current_user: RequireAuth,
    pool: DbPool,
) -> Response:
    await upsert_cart_item(pool, current_user.id, product_id, payload.quantity)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@router.put("", status_code=http_status.HTTP_204_NO_CONTENT)
async def set_cart_items(
    payload: CartItemsUpsert,
    current_user: RequireAuth,
    pool: DbPool,
) -> Response:
    await upsert_cart_items(pool, current_user.id, payload.items)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@router.delete("/{product_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_cart_item(
    product_id: UUID,
    current_user: RequireAuth,
    pool: DbPool,
) -> Response:
    await remove_cart_item(pool, current_user.id, product_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@router.delete("", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_cart(
    current_user: RequireAuth,
    pool: DbPool,
) -> Response:
    await clear_cart(pool, current_user.id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
