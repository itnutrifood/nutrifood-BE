from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg

from backend.apps.common.enums import LanguageCode
from backend.apps.common.exceptions import InvalidCursorError
from backend.apps.common.pagination import (
    CursorPage,
    decode_cursor,
    encode_cursor,
)
from backend.apps.favorites import repository
from backend.apps.favorites.exceptions import FavoriteProductNotFoundError
from backend.apps.products.schemas import PublicProductRead
from backend.apps.products.service import to_public_product


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
    parsed_cursor: FavoriteCursor | None = None
    if cursor is not None:
        parsed_cursor = _parse_favorite_cursor(cursor)

    favorite_products = await repository.list_favorite_products(
        pool,
        user_id,
        limit,
        (parsed_cursor.created_at, parsed_cursor.product_id) if parsed_cursor is not None else None,
    )
    next_cursor = None
    if len(favorite_products) > limit:
        last_product, favorited_at = favorite_products[limit - 1]
        next_cursor = _favorite_cursor(
            favorited_at,
            last_product.id,
        )

    return CursorPage(
        items=[
            to_public_product(product, language)
            for product, _favorited_at in favorite_products[:limit]
        ],
        limit=limit,
        next_cursor=next_cursor,
    )


async def add_favorite_product(
    pool: asyncpg.Pool,
    user_id: UUID,
    product_id: UUID,
) -> None:
    product_exists = await repository.add_favorite_product(
        pool,
        user_id,
        product_id,
    )
    if not product_exists:
        raise FavoriteProductNotFoundError([product_id])


async def add_favorite_products(
    pool: asyncpg.Pool,
    user_id: UUID,
    product_ids: Sequence[UUID],
) -> None:
    missing_product_ids = await repository.add_favorite_products(
        pool,
        user_id,
        product_ids,
    )
    if missing_product_ids:
        raise FavoriteProductNotFoundError(missing_product_ids)


async def remove_favorite_product(
    pool: asyncpg.Pool,
    user_id: UUID,
    product_id: UUID,
) -> None:
    await repository.remove_favorite_product(pool, user_id, product_id)
