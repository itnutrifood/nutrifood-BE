from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import status as http_status

from backend.apps.accounts.auth import RequireAuth
from backend.apps.cart.schemas import CartItemsUpsert, CartItemUpsert, CartRead
from backend.apps.cart.service import (
    CartProductNotFoundError,
    clear_cart,
    get_cart,
    remove_cart_item,
    upsert_cart_item,
    upsert_cart_items,
)
from backend.apps.common.localization import LocaleFromPath
from backend.config.database import get_pool

DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]

router = APIRouter(prefix="/cart", tags=["cart"])


def _product_not_found_error(exc: CartProductNotFoundError) -> HTTPException:
    return HTTPException(
        status_code=http_status.HTTP_404_NOT_FOUND,
        detail={
            "message": "One or more products were not found",
            "product_ids": [str(product_id) for product_id in exc.product_ids],
        },
    )


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
    try:
        await upsert_cart_item(pool, current_user.id, product_id, payload.quantity)
    except CartProductNotFoundError as exc:
        raise _product_not_found_error(exc) from exc
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@router.put("", status_code=http_status.HTTP_204_NO_CONTENT)
async def set_cart_items(
    payload: CartItemsUpsert,
    current_user: RequireAuth,
    pool: DbPool,
) -> Response:
    try:
        await upsert_cart_items(pool, current_user.id, payload.items)
    except CartProductNotFoundError as exc:
        raise _product_not_found_error(exc) from exc
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
