from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

import asyncpg

from backend.apps.admin.products import PRODUCT_COLUMNS, ProductRead, _product_from_record
from backend.apps.common.enums import LanguageCode
from backend.apps.common.pagination import (
    CursorPage,
    InvalidCursorError,
    decode_cursor,
    encode_cursor,
)
from backend.apps.products.schemas import PublicProductRead
from backend.apps.products.service import to_public_product


class FavoriteProductNotFoundError(Exception):
    def __init__(self, product_ids: Sequence[UUID]) -> None:
        self.product_ids = list(product_ids)
        super().__init__("One or more products were not found")


@dataclass(frozen=True)
class FavoriteCursor:
    created_at: datetime
    product_id: UUID


def _parse_favorite_cursor(cursor: str) -> FavoriteCursor:
    payload = decode_cursor(cursor)
    created_at = payload.get("created_at")
    product_id = payload.get("product_id")

    if not isinstance(created_at, str) or not created_at:
        raise InvalidCursorError("Invalid favorite cursor")
    if not isinstance(product_id, str):
        raise InvalidCursorError("Invalid favorite cursor")

    try:
        parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        parsed_product_id = UUID(product_id)
    except ValueError as exc:
        raise InvalidCursorError("Invalid favorite cursor") from exc

    if parsed_created_at.tzinfo is None:
        raise InvalidCursorError("Invalid favorite cursor")

    return FavoriteCursor(created_at=parsed_created_at, product_id=parsed_product_id)


def _favorite_cursor(created_at: datetime, product_id: UUID) -> str:
    return encode_cursor({"created_at": created_at, "product_id": product_id})


async def list_favorite_products(
    pool: asyncpg.Pool,
    user_id: UUID,
    language: LanguageCode,
    limit: int,
    cursor: str | None,
) -> CursorPage[PublicProductRead]:
    params: list[object] = [user_id]
    cursor_condition = ""

    if cursor is not None:
        favorite_cursor = _parse_favorite_cursor(cursor)
        params.extend([favorite_cursor.created_at, favorite_cursor.product_id])
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

    page_rows = rows[:limit]
    products: list[ProductRead] = [_product_from_record(row) for row in page_rows]
    next_cursor = None
    if len(rows) > limit:
        last_row = page_rows[-1]
        next_cursor = _favorite_cursor(
            cast(datetime, last_row["favorited_at"]),
            cast(UUID, last_row["id"]),
        )

    return CursorPage(
        items=[to_public_product(product, language) for product in products],
        limit=limit,
        next_cursor=next_cursor,
    )


async def add_favorite_product(
    pool: asyncpg.Pool,
    user_id: UUID,
    product_id: UUID,
) -> None:
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
    if product_exists is not True:
        raise FavoriteProductNotFoundError([product_id])


async def add_favorite_products(
    pool: asyncpg.Pool,
    user_id: UUID,
    product_ids: Sequence[UUID],
) -> None:
    missing_product_ids = cast(
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
    if missing_product_ids:
        raise FavoriteProductNotFoundError(missing_product_ids)


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
