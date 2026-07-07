from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast
from uuid import UUID

import asyncpg

from backend.apps.admin.categories import CATEGORY_COLUMNS, CategoryRead, _category_from_record
from backend.apps.categories.schemas import PublicCategoryRead
from backend.apps.common.enums import CategoryStatus, LanguageCode
from backend.apps.common.localization import localized_text, required_localized_text
from backend.apps.common.pagination import (
    CursorPage,
    InvalidCursorError,
    decode_cursor,
    encode_cursor,
)


class PublicCategoryNotFoundError(Exception):
    pass


class CategoryFilterConflictError(ValueError):
    pass


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

    params: list[object] = [CategoryStatus.ACTIVE.value]
    conditions = ["status = $1::category_status"]

    if root_only:
        conditions.append("parent_id IS NULL")
    elif parent_id is not None:
        params.append(parent_id)
        conditions.append(f"parent_id = ${len(params)}")

    if cursor is not None:
        category_cursor = _parse_category_cursor(cursor)
        params.extend([category_cursor.sort_order, category_cursor.slug, category_cursor.id])
        conditions.append(
            f"(sort_order, slug, id) > (${len(params) - 2}, ${len(params) - 1}, ${len(params)})"
        )

    params.append(limit + 1)
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {CATEGORY_COLUMNS}
            FROM categories
            WHERE {" AND ".join(conditions)}
            ORDER BY sort_order, slug, id
            LIMIT ${len(params)}
            """,
            *params,
        ),
    )

    categories = [_category_from_record(row) for row in rows[:limit]]
    next_cursor = _category_cursor(categories[-1]) if len(rows) > limit else None

    return CursorPage(
        items=[_public_category(category, language) for category in categories],
        limit=limit,
        next_cursor=next_cursor,
    )


async def get_public_category(
    pool: asyncpg.Pool,
    language: LanguageCode,
    category_id: UUID,
) -> PublicCategoryRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {CATEGORY_COLUMNS}
            FROM categories
            WHERE id = $1
                AND status = $2::category_status
            """,
            category_id,
            CategoryStatus.ACTIVE.value,
        ),
    )
    if row is None:
        raise PublicCategoryNotFoundError

    return _public_category(_category_from_record(row), language)


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
