from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

import asyncpg

from backend.apps.products.repository import PRODUCT_COLUMNS, product_from_record
from backend.apps.products.schemas import ProductRead


async def list_favorite_products(
    pool: asyncpg.Pool,
    user_id: UUID,
    limit: int,
    cursor: tuple[datetime, UUID] | None,
) -> list[tuple[ProductRead, datetime]]:
    params: list[object] = [user_id]
    cursor_condition = ""

    if cursor is not None:
        params.extend(cursor)
        cursor_condition = """
            AND (uf.created_at, uf.product_id) < ($2, $3)
        """

    params.append(limit + 1)
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {PRODUCT_COLUMNS},
                uf.created_at AS favorited_at
            FROM user_favorite_products AS uf
            INNER JOIN products AS p ON p.id = uf.product_id
            WHERE uf.user_id = $1
            {cursor_condition}
            ORDER BY uf.created_at DESC, uf.product_id DESC
            LIMIT ${len(params)}
            """,
            *params,
        ),
    )
    return [(product_from_record(row), cast(datetime, row["favorited_at"])) for row in rows]


async def add_favorite_product(
    pool: asyncpg.Pool,
    user_id: UUID,
    product_id: UUID,
) -> bool:
    product_exists = await pool.fetchval(
        """
        WITH matching_product AS (
            SELECT id
            FROM products
            WHERE id = $2
        ), inserted_favorite AS (
            INSERT INTO user_favorite_products (user_id, product_id)
            SELECT $1, id
            FROM matching_product
            ON CONFLICT (user_id, product_id) DO NOTHING
            RETURNING product_id
        )
        SELECT EXISTS (SELECT 1 FROM matching_product)
        """,
        user_id,
        product_id,
    )
    return product_exists is True


async def add_favorite_products(
    pool: asyncpg.Pool,
    user_id: UUID,
    product_ids: Sequence[UUID],
) -> list[UUID]:
    return list(
        cast(
            Sequence[UUID],
            await pool.fetchval(
                """
                WITH requested_products AS (
                    SELECT DISTINCT unnest($2::uuid[]) AS product_id
                ), matching_products AS (
                    SELECT requested.product_id
                    FROM requested_products AS requested
                    INNER JOIN products AS p ON p.id = requested.product_id
                ), inserted_favorites AS (
                    INSERT INTO user_favorite_products (user_id, product_id)
                    SELECT $1, matching.product_id
                    FROM matching_products AS matching
                    WHERE
                        (SELECT count(*) FROM matching_products)
                        = (SELECT count(*) FROM requested_products)
                    ON CONFLICT (user_id, product_id) DO NOTHING
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
                list(product_ids),
            ),
        )
    )


async def remove_favorite_product(
    pool: asyncpg.Pool,
    user_id: UUID,
    product_id: UUID,
) -> None:
    await pool.execute(
        """
        DELETE FROM user_favorite_products
        WHERE user_id = $1 AND product_id = $2
        """,
        user_id,
        product_id,
    )
