from dataclasses import dataclass
from uuid import UUID

import asyncpg

from backend.apps.categories import repository
from backend.apps.categories.exceptions import (
    CategoryFilterConflictError,
    CategoryNotFoundError,
)
from backend.apps.categories.schemas import CategoryRead, PublicCategoryRead
from backend.apps.common.enums import LanguageCode
from backend.apps.common.exceptions import InvalidCursorError
from backend.apps.common.localization import localized_text, required_localized_text
from backend.apps.common.pagination import (
    CursorPage,
    decode_cursor,
    encode_cursor,
)

PublicCategoryNotFoundError = CategoryNotFoundError


@dataclass(frozen=True)
class CategoryCursor:
    sort_order: int
    slug: str
    id: UUID


def _parse_category_cursor(cursor: str) -> CategoryCursor:
    payload = decode_cursor(cursor)

    sort_order = payload.get("sort_order")
    slug = payload.get("slug")
    category_id = payload.get("id")

    if isinstance(sort_order, bool) or not isinstance(sort_order, int):
        raise InvalidCursorError("Invalid category cursor")
    if not isinstance(slug, str) or not slug:
        raise InvalidCursorError("Invalid category cursor")
    if not isinstance(category_id, str):
        raise InvalidCursorError("Invalid category cursor")

    try:
        parsed_category_id = UUID(category_id)
    except ValueError as exc:
        raise InvalidCursorError("Invalid category cursor") from exc

    return CategoryCursor(sort_order=sort_order, slug=slug, id=parsed_category_id)


def _category_cursor(category: CategoryRead) -> str:
    return encode_cursor(
        {
            "sort_order": category.sort_order,
            "slug": category.slug,
            "id": category.id,
        }
    )


async def list_public_categories(
    pool: asyncpg.Pool,
    language: LanguageCode,
    parent_id: UUID | None,
    root_only: bool,
    limit: int,
    cursor: str | None,
) -> CursorPage[PublicCategoryRead]:
    if root_only and parent_id is not None:
        raise CategoryFilterConflictError("root_only and parent_id cannot be used together")

    parsed_cursor: CategoryCursor | None = None
    if cursor is not None:
        parsed_cursor = _parse_category_cursor(cursor)

    categories = await repository.list_active_categories(
        pool,
        parent_id,
        root_only,
        limit,
        (parsed_cursor.sort_order, parsed_cursor.slug, parsed_cursor.id)
        if parsed_cursor is not None
        else None,
    )
    next_cursor = _category_cursor(categories[limit - 1]) if len(categories) > limit else None

    return CursorPage(
        items=[_public_category(category, language) for category in categories[:limit]],
        limit=limit,
        next_cursor=next_cursor,
    )


async def get_public_category(
    pool: asyncpg.Pool,
    language: LanguageCode,
    category_id: UUID,
) -> PublicCategoryRead:
    category = await repository.get_active_category(pool, category_id)
    return _public_category(category, language)


def _public_category(category: CategoryRead, language: LanguageCode) -> PublicCategoryRead:
    return PublicCategoryRead(
        id=category.id,
        parent_id=category.parent_id,
        slug=category.slug,
        name=required_localized_text(category.name.to_db(), language),
        description=localized_text(category.description.to_db(), language),
        status=category.status,
        sort_order=category.sort_order,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )
