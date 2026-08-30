import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
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
from backend.apps.products.schemas import ProductRead, ProductSort, PublicProductRead

PublicProductNotFoundError = ProductNotFoundError


@dataclass(frozen=True)
class ProductCursor:
    created_at: datetime
    id: UUID


@dataclass(frozen=True)
class ProductPriceCursor:
    price: Decimal
    id: UUID


def _parse_product_cursor(cursor: str) -> ProductCursor:
    payload = decode_cursor(cursor)

    if set(payload) != {"created_at", "id"}:
        raise InvalidCursorError("Invalid product cursor")

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


def _price_filter_fingerprint(
    language: LanguageCode,
    sort: ProductSort,
    search: str | None,
    category_id: UUID | None,
) -> str:
    canonical_filters = json.dumps(
        [
            language.value,
            sort.value,
            search.casefold() if search is not None else None,
            str(category_id) if category_id is not None else None,
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_filters.encode("utf-8")).hexdigest()


def _parse_product_price_cursor(
    cursor: str,
    expected_sort: ProductSort,
    expected_filter_fingerprint: str,
) -> ProductPriceCursor:
    payload = decode_cursor(cursor)
    expected_keys = {"kind", "sort", "price", "id", "filter_fingerprint"}

    if (
        set(payload) != expected_keys
        or payload.get("kind") != "product-price-v1"
        or payload.get("sort") != expected_sort.value
        or payload.get("filter_fingerprint") != expected_filter_fingerprint
    ):
        raise InvalidCursorError("Invalid product price cursor")

    price = payload.get("price")
    product_id = payload.get("id")
    if not isinstance(price, str) or not isinstance(product_id, str):
        raise InvalidCursorError("Invalid product price cursor")

    try:
        parsed_price = Decimal(price)
        parsed_product_id = UUID(product_id)
    except (InvalidOperation, ValueError) as exc:
        raise InvalidCursorError("Invalid product price cursor") from exc

    if not parsed_price.is_finite() or parsed_price < 0:
        raise InvalidCursorError("Invalid product price cursor")

    return ProductPriceCursor(price=parsed_price, id=parsed_product_id)


def _product_price_cursor(
    product: ProductRead,
    sort: ProductSort,
    filter_fingerprint: str,
) -> str:
    return encode_cursor(
        {
            "kind": "product-price-v1",
            "sort": sort.value,
            "price": product.price,
            "id": product.id,
            "filter_fingerprint": filter_fingerprint,
        }
    )


def _search_filter_fingerprint(
    language: LanguageCode,
    search: str,
    category_id: UUID | None,
) -> str:
    canonical_filters = json.dumps(
        [language.value, search.casefold(), str(category_id) if category_id is not None else None],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_filters.encode("utf-8")).hexdigest()


def _parse_product_search_cursor(
    cursor: str,
    expected_filter_fingerprint: str,
) -> repository.ProductSearchPosition:
    payload = decode_cursor(cursor)
    expected_keys = {
        "kind",
        "exact_title_rank",
        "title_match_rank",
        "search_rank",
        "created_at",
        "id",
        "filter_fingerprint",
    }
    if set(payload) != expected_keys or payload.get("kind") != "product-search-v1":
        raise InvalidCursorError("Invalid product search cursor")

    exact_title_rank = payload.get("exact_title_rank")
    title_match_rank = payload.get("title_match_rank")
    search_rank = payload.get("search_rank")
    created_at = payload.get("created_at")
    product_id = payload.get("id")
    filter_fingerprint = payload.get("filter_fingerprint")

    if type(exact_title_rank) is not int or exact_title_rank not in {0, 1}:
        raise InvalidCursorError("Invalid product search cursor")
    if type(title_match_rank) is not int or title_match_rank not in {0, 1}:
        raise InvalidCursorError("Invalid product search cursor")
    if not isinstance(search_rank, str):
        raise InvalidCursorError("Invalid product search cursor")
    if not isinstance(created_at, str) or not created_at:
        raise InvalidCursorError("Invalid product search cursor")
    if not isinstance(product_id, str):
        raise InvalidCursorError("Invalid product search cursor")
    if filter_fingerprint != expected_filter_fingerprint:
        raise InvalidCursorError("Invalid product search cursor")

    try:
        parsed_search_rank = Decimal(search_rank)
        parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        parsed_product_id = UUID(product_id)
    except (InvalidOperation, ValueError) as exc:
        raise InvalidCursorError("Invalid product search cursor") from exc

    if not parsed_search_rank.is_finite() or parsed_search_rank < 0:
        raise InvalidCursorError("Invalid product search cursor")
    if parsed_created_at.tzinfo is None:
        raise InvalidCursorError("Invalid product search cursor")

    return repository.ProductSearchPosition(
        exact_title_rank=exact_title_rank,
        title_match_rank=title_match_rank,
        search_rank=parsed_search_rank,
        created_at=parsed_created_at,
        id=parsed_product_id,
    )


def _product_search_cursor(
    result: repository.ProductSearchResult,
    filter_fingerprint: str,
) -> str:
    return encode_cursor(
        {
            "kind": "product-search-v1",
            "exact_title_rank": result.position.exact_title_rank,
            "title_match_rank": result.position.title_match_rank,
            "search_rank": result.position.search_rank,
            "created_at": result.position.created_at,
            "id": result.position.id,
            "filter_fingerprint": filter_fingerprint,
        }
    )


async def list_public_products(
    pool: asyncpg.Pool,
    language: LanguageCode,
    category_id: UUID | None,
    limit: int,
    cursor: str | None,
    search: str | None,
    sort: ProductSort | None = None,
) -> CursorPage[PublicProductRead]:
    normalized_search = " ".join(search.split()) if search is not None else None

    if sort is not None:
        filter_fingerprint = _price_filter_fingerprint(
            language,
            sort,
            normalized_search,
            category_id,
        )
        parsed_price_cursor: ProductPriceCursor | None = None
        if cursor is not None:
            parsed_price_cursor = _parse_product_price_cursor(
                cursor,
                sort,
                filter_fingerprint,
            )

        products = await repository.list_public_products_by_price(
            pool=pool,
            language=language,
            search=normalized_search,
            category_id=category_id,
            sort=sort,
            limit=limit,
            cursor=(parsed_price_cursor.price, parsed_price_cursor.id)
            if parsed_price_cursor is not None
            else None,
        )
        next_cursor = (
            _product_price_cursor(products[limit - 1], sort, filter_fingerprint)
            if len(products) > limit
            else None
        )
        return CursorPage(
            items=[to_public_product(product, language) for product in products[:limit]],
            limit=limit,
            next_cursor=next_cursor,
        )

    if normalized_search is not None:
        filter_fingerprint = _search_filter_fingerprint(
            language,
            normalized_search,
            category_id,
        )
        parsed_search_cursor: repository.ProductSearchPosition | None = None
        if cursor is not None:
            parsed_search_cursor = _parse_product_search_cursor(cursor, filter_fingerprint)

        results = await repository.search_public_products(
            pool=pool,
            language=language,
            search=normalized_search,
            category_id=category_id,
            limit=limit,
            cursor=parsed_search_cursor,
        )
        next_cursor = (
            _product_search_cursor(results[limit - 1], filter_fingerprint)
            if len(results) > limit
            else None
        )
        return CursorPage(
            items=[to_public_product(result.product, language) for result in results[:limit]],
            limit=limit,
            next_cursor=next_cursor,
        )

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


async def get_public_product_by_slug(
    pool: asyncpg.Pool,
    language: LanguageCode,
    slug: str,
) -> PublicProductRead:
    product = await repository.get_public_product_by_slug(pool, slug)
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
