from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg

from backend.apps.common.enums import LanguageCode
from backend.apps.common.exceptions import InvalidCursorError
from backend.apps.common.localization import (
    localized_items,
    localized_text,
    required_localized_text,
)
from backend.apps.common.pagination import (
    CursorPage,
    decode_cursor,
    encode_cursor,
)
from backend.apps.products import repository
from backend.apps.products.exceptions import ProductNotFoundError
from backend.apps.products.schemas import ProductRead, PublicProductRead

PublicProductNotFoundError = ProductNotFoundError


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
    parsed_cursor: ProductCursor | None = None
    if cursor is not None:
        parsed_cursor = _parse_product_cursor(cursor)

    products = await repository.list_public_products(
        pool,
        category_id,
        limit,
        (parsed_cursor.created_at, parsed_cursor.id) if parsed_cursor is not None else None,
    )
    next_cursor = _product_cursor(products[limit - 1]) if len(products) > limit else None

    return CursorPage(
        items=[to_public_product(product, language) for product in products[:limit]],
        limit=limit,
        next_cursor=next_cursor,
    )


async def get_public_product(
    pool: asyncpg.Pool,
    language: LanguageCode,
    product_id: UUID,
) -> PublicProductRead:
    product = await repository.get_public_product(pool, product_id)
    return to_public_product(product, language)


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
