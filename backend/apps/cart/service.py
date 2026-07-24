from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import cast
from uuid import UUID

import asyncpg

from backend.apps.admin.products import PRODUCT_COLUMNS, ProductRead, _product_from_record
from backend.apps.cart.schemas import CartItemBatchUpsert, CartItemRead, CartRead
from backend.apps.common.enums import LanguageCode
from backend.apps.products.service import to_public_product


class CartProductNotFoundError(Exception):
    def __init__(self, product_ids: Sequence[UUID]) -> None:
        self.product_ids = list(product_ids)
        super().__init__("One or more products were not found")


async def get_cart(
    pool: asyncpg.Pool,
    user_id: UUID,
    language: LanguageCode,
) -> CartRead:
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {PRODUCT_COLUMNS},
                ci.quantity
            FROM user_cart_items AS ci
            INNER JOIN products AS p ON p.id = ci.product_id
            WHERE ci.user_id = $1
            ORDER BY ci.created_at DESC, ci.product_id DESC
            """,
            user_id,
        ),
    )

    items: list[CartItemRead] = []
    for row in rows:
        product: ProductRead = _product_from_record(row)
        quantity = cast(int, row["quantity"])
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
    product_exists = await pool.fetchval(
        """
        WITH matching_product AS (
            SELECT id
            FROM products
            WHERE id = $2
        ), upserted_cart_item AS (
            INSERT INTO user_cart_items (user_id, product_id, quantity)
            SELECT $1, id, $3
            FROM matching_product
            ON CONFLICT (user_id, product_id) DO UPDATE
            SET quantity = EXCLUDED.quantity,
                updated_at = now()
            RETURNING product_id
        )
        SELECT EXISTS (SELECT 1 FROM matching_product)
        """,
        user_id,
        product_id,
        quantity,
    )
    if product_exists is not True:
        raise CartProductNotFoundError([product_id])


async def upsert_cart_items(
    pool: asyncpg.Pool,
    user_id: UUID,
    items: Sequence[CartItemBatchUpsert],
) -> None:
    product_ids = [item.product_id for item in items]
    quantities = [item.quantity for item in items]
    missing_product_ids = cast(
        Sequence[UUID],
        await pool.fetchval(
            """
            WITH requested_products AS (
                SELECT product_id, quantity
                FROM unnest($2::uuid[], $3::integer[]) AS requested(product_id, quantity)
            ), matching_products AS (
                SELECT requested.product_id, requested.quantity
                FROM requested_products AS requested
                INNER JOIN products AS p ON p.id = requested.product_id
            ), upserted_cart_items AS (
                INSERT INTO user_cart_items (user_id, product_id, quantity)
                SELECT $1, matching.product_id, matching.quantity
                FROM matching_products AS matching
                WHERE
                    (SELECT count(*) FROM matching_products)
                    = (SELECT count(*) FROM requested_products)
                ON CONFLICT (user_id, product_id) DO UPDATE
                SET quantity = EXCLUDED.quantity,
                    updated_at = now()
                RETURNING product_id
            )
            SELECT COALESCE(
                array_agg(requested.product_id ORDER BY requested.product_id)
                    FILTER (WHERE matching.product_id IS NULL),
                ARRAY[]::uuid[]
            )
            FROM requested_products AS requested
            LEFT JOIN matching_products AS matching
                ON matching.product_id = requested.product_id
            """,
            user_id,
            product_ids,
            quantities,
        ),
    )
    if missing_product_ids:
        raise CartProductNotFoundError(missing_product_ids)


async def remove_cart_item(
    pool: asyncpg.Pool,
    user_id: UUID,
    product_id: UUID,
) -> None:
    await pool.execute(
        """
        DELETE FROM user_cart_items
        WHERE user_id = $1 AND product_id = $2
        """,
        user_id,
        product_id,
    )


async def clear_cart(pool: asyncpg.Pool, user_id: UUID) -> None:
    await pool.execute(
        """
        DELETE FROM user_cart_items
        WHERE user_id = $1
        """,
        user_id,
    )
