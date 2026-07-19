from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

import asyncpg

from backend.apps.admin.products import PRODUCT_COLUMNS, ProductRead, _product_from_record
from backend.apps.common.enums import CategoryStatus, LanguageCode
from backend.apps.common.localization import (
    localized_items,
    localized_text,
    required_localized_text,
)
from backend.apps.common.pagination import (
    CursorPage,
    InvalidCursorError,
    decode_cursor,
    encode_cursor,
)
from backend.apps.products.schemas import PublicProductRead


class PublicProductNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class ProductCursor:
    created_at: datetime
    id: UUID


def _parse_product_cursor(cursor: str) -> ProductCursor:
    payload = decode_cursor(cursor)

    created_at = payload.get("created_at")
    product_id = payload.get("id")

    if not isinstance(created_at, str) or not created_at:
        raise InvalidCursorError("Invalid product cursor")
    if not isinstance(product_id, str):
        raise InvalidCursorError("Invalid product cursor")

    try:
        parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        parsed_product_id = UUID(product_id)
    except ValueError as exc:
        raise InvalidCursorError("Invalid product cursor") from exc

    if parsed_created_at.tzinfo is None:
        raise InvalidCursorError("Invalid product cursor")

    return ProductCursor(created_at=parsed_created_at, id=parsed_product_id)


def _product_cursor(product: ProductRead) -> str:
    return encode_cursor({"created_at": product.created_at, "id": product.id})


async def list_public_products(
    pool: asyncpg.Pool,
    language: LanguageCode,
    category_id: UUID | None,
    limit: int,
    cursor: str | None,
) -> CursorPage[PublicProductRead]:
    params: list[object] = []
    conditions: list[str] = []

    if category_id is not None:
        params.append(category_id)
        category_id_param = len(params)
        params.append(CategoryStatus.ACTIVE.value)
        status_param = len(params)
        conditions.append(
            f"""
            EXISTS (
                SELECT 1
                FROM product_categories AS pc
                INNER JOIN categories AS c ON c.id = pc.category_id
                WHERE pc.product_id = p.id
                    AND pc.category_id = ${category_id_param}
                    AND c.status = ${status_param}::category_status
            )
            """
        )

    if cursor is not None:
        product_cursor = _parse_product_cursor(cursor)
        params.extend([product_cursor.created_at, product_cursor.id])
        created_at_param = len(params) - 1
        id_param = len(params)
        conditions.append(
            f"""
            (
                p.created_at < ${created_at_param}
                OR (p.created_at = ${created_at_param} AND p.id > ${id_param})
            )
            """
        )

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    params.append(limit + 1)
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {PRODUCT_COLUMNS}
            FROM products AS p
            {where_clause}
            ORDER BY p.created_at DESC, p.id
            LIMIT ${len(params)}
            """,
            *params,
        ),
    )

    products = [_product_from_record(row) for row in rows[:limit]]
    next_cursor = _product_cursor(products[-1]) if len(rows) > limit else None

    return CursorPage(
        items=[to_public_product(product, language) for product in products],
        limit=limit,
        next_cursor=next_cursor,
    )


async def get_public_product(
    pool: asyncpg.Pool,
    language: LanguageCode,
    product_id: UUID,
) -> PublicProductRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {PRODUCT_COLUMNS}
            FROM products AS p
            WHERE p.id = $1
            """,
            product_id,
        ),
    )
    if row is None:
        raise PublicProductNotFoundError

    return to_public_product(_product_from_record(row), language)


def to_public_product(product: ProductRead, language: LanguageCode) -> PublicProductRead:
    return PublicProductRead(
        id=product.id,
        slug=product.slug,
        title=required_localized_text(product.title.to_db(), language),
        description=required_localized_text(product.description.to_db(), language),
        images=product.images,
        category_ids=product.category_ids,
        image_tags=localized_items(product.image_tags.to_db(), language),
        text_tags=localized_items(product.text_tags.to_db(), language),
        serving_size=localized_text(product.serving_size.to_db(), language),
        readiness_time_minutes=product.readiness_time_minutes,
        price=product.price,
        allergens=localized_items(product.allergens.to_db(), language),
        allergen_information=localized_text(product.allergen_information.to_db(), language),
        storage_delivery=localized_text(product.storage_delivery.to_db(), language),
        created_at=product.created_at,
        updated_at=product.updated_at,
    )
