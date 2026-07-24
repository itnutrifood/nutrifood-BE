from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

import asyncpg

from backend.apps.cart import repository
from backend.apps.cart.exceptions import CartProductNotFoundError
from backend.apps.cart.schemas import CartItemBatchUpsert, CartItemRead, CartRead
from backend.apps.common.enums import LanguageCode
from backend.apps.products.service import to_public_product


async def get_cart(
    pool: asyncpg.Pool,
    user_id: UUID,
    language: LanguageCode,
) -> CartRead:
    items: list[CartItemRead] = []
    for product, quantity in await repository.get_cart_items(pool, user_id):
        items.append(
            CartItemRead(
                product=to_public_product(product, language),
                quantity=quantity,
                line_total=product.price * quantity,
            )
        )

    return CartRead(
        items=items,
        total_quantity=sum(item.quantity for item in items),
        subtotal=sum((item.line_total for item in items), start=Decimal()),
    )


async def upsert_cart_item(
    pool: asyncpg.Pool,
    user_id: UUID,
    product_id: UUID,
    quantity: int,
) -> None:
    product_exists = await repository.upsert_cart_item(
        pool,
        user_id,
        product_id,
        quantity,
    )
    if not product_exists:
        raise CartProductNotFoundError([product_id])


async def upsert_cart_items(
    pool: asyncpg.Pool,
    user_id: UUID,
    items: Sequence[CartItemBatchUpsert],
) -> None:
    missing_product_ids = await repository.upsert_cart_items(pool, user_id, items)
    if missing_product_ids:
        raise CartProductNotFoundError(missing_product_ids)


async def remove_cart_item(
    pool: asyncpg.Pool,
    user_id: UUID,
    product_id: UUID,
) -> None:
    await repository.remove_cart_item(pool, user_id, product_id)


async def clear_cart(pool: asyncpg.Pool, user_id: UUID) -> None:
    await repository.clear_cart(pool, user_id)
