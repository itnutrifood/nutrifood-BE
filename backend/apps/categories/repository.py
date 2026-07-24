import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import asyncpg

from backend.apps.categories.exceptions import (
    CategoryDeleteConflictError,
    CategoryNotFoundError,
    DuplicateCategorySlugError,
    ParentCategoryNotFoundError,
)
from backend.apps.categories.schemas import (
    CategoryCreate,
    CategoryListResponse,
    CategoryRead,
    CategoryUpdate,
    LocalizedDescription,
    LocalizedName,
)
from backend.apps.common.db import json_object, rows_affected
from backend.apps.common.enums import CategoryStatus
from backend.apps.common.pagination import page_count, page_offset

CATEGORY_COLUMNS = """
    id,
    parent_id,
    slug,
    name,
    description,
    status::text AS status,
    sort_order,
    created_at,
    updated_at
"""


def category_from_record(record: Mapping[str, object]) -> CategoryRead:
    return CategoryRead(
        id=cast(UUID, record["id"]),
        parent_id=cast(UUID | None, record["parent_id"]),
        slug=cast(str, record["slug"]),
        name=LocalizedName.model_validate(json_object(record["name"])),
        description=LocalizedDescription.model_validate(json_object(record["description"])),
        status=CategoryStatus(cast(str, record["status"])),
        sort_order=cast(int, record["sort_order"]),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


async def category_exists(pool: asyncpg.Pool, category_id: UUID) -> bool:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            "SELECT EXISTS(SELECT 1 FROM categories WHERE id = $1) AS exists", category_id
        ),
    )
    return bool(row and row["exists"])


async def is_descendant(pool: asyncpg.Pool, category_id: UUID, parent_id: UUID) -> bool:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            """
            WITH RECURSIVE descendants AS (
                SELECT id
                FROM categories
                WHERE parent_id = $1
                UNION ALL
                SELECT categories.id
                FROM categories
                INNER JOIN descendants ON categories.parent_id = descendants.id
            )
            SELECT EXISTS(SELECT 1 FROM descendants WHERE id = $2) AS exists
            """,
            category_id,
            parent_id,
        ),
    )
    return bool(row and row["exists"])


async def create_category(pool: asyncpg.Pool, payload: CategoryCreate) -> CategoryRead:
    try:
        row = cast(
            Mapping[str, object] | None,
            await pool.fetchrow(
                f"""
                INSERT INTO categories (
                    parent_id,
                    slug,
                    name,
                    description,
                    status,
                    sort_order
                )
                VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::category_status, $6)
                RETURNING {CATEGORY_COLUMNS}
                """,
                payload.parent_id,
                payload.slug,
                json.dumps(payload.name.to_db()),
                json.dumps(payload.description.to_db()),
                payload.status.value,
                payload.sort_order,
            ),
        )
    except asyncpg.UniqueViolationError as exc:
        raise DuplicateCategorySlugError from exc
    except asyncpg.ForeignKeyViolationError as exc:
        raise ParentCategoryNotFoundError from exc

    if row is None:
        raise RuntimeError("Category insert did not return a row")

    return category_from_record(row)


async def get_category(pool: asyncpg.Pool, category_id: UUID) -> CategoryRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {CATEGORY_COLUMNS}
            FROM categories
            WHERE id = $1
            """,
            category_id,
        ),
    )
    if row is None:
        raise CategoryNotFoundError

    return category_from_record(row)


async def list_categories(
    pool: asyncpg.Pool,
    status_filter: CategoryStatus | None,
    parent_id: UUID | None,
    root_only: bool,
    page: int,
    limit: int,
) -> CategoryListResponse:
    conditions: list[str] = []
    params: list[Any] = []

    if status_filter is not None:
        params.append(status_filter.value)
        conditions.append(f"status = ${len(params)}::category_status")

    if root_only:
        conditions.append("parent_id IS NULL")
    elif parent_id is not None:
        params.append(parent_id)
        conditions.append(f"parent_id = ${len(params)}")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    count_row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(f"SELECT count(*) AS total FROM categories {where_clause}", *params),
    )
    total = cast(int, count_row["total"]) if count_row is not None else 0

    params.extend([limit, page_offset(page, limit)])
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {CATEGORY_COLUMNS}
            FROM categories
            {where_clause}
            ORDER BY parent_id NULLS FIRST, sort_order, slug
            LIMIT ${len(params) - 1}
            OFFSET ${len(params)}
            """,
            *params,
        ),
    )

    return CategoryListResponse(
        items=[category_from_record(row) for row in rows],
        total=total,
        page=page,
        limit=limit,
        total_pages=page_count(total, limit),
    )


async def update_category(
    pool: asyncpg.Pool,
    category_id: UUID,
    payload: CategoryUpdate,
) -> CategoryRead:
    assignments: list[str] = []
    params: list[Any] = []

    if "parent_id" in payload.model_fields_set:
        params.append(payload.parent_id)
        assignments.append(f"parent_id = ${len(params)}")
    if "slug" in payload.model_fields_set:
        params.append(payload.slug)
        assignments.append(f"slug = ${len(params)}")
    if "name" in payload.model_fields_set:
        params.append(json.dumps(cast(LocalizedName, payload.name).to_db()))
        assignments.append(f"name = ${len(params)}::jsonb")
    if "description" in payload.model_fields_set:
        params.append(json.dumps(cast(LocalizedDescription, payload.description).to_db()))
        assignments.append(f"description = ${len(params)}::jsonb")
    if "status" in payload.model_fields_set:
        params.append(cast(CategoryStatus, payload.status).value)
        assignments.append(f"status = ${len(params)}::category_status")
    if "sort_order" in payload.model_fields_set:
        params.append(payload.sort_order)
        assignments.append(f"sort_order = ${len(params)}")

    params.append(category_id)

    try:
        row = cast(
            Mapping[str, object] | None,
            await pool.fetchrow(
                f"""
                UPDATE categories
                SET {", ".join(assignments)}
                WHERE id = ${len(params)}
                RETURNING {CATEGORY_COLUMNS}
                """,
                *params,
            ),
        )
    except asyncpg.UniqueViolationError as exc:
        raise DuplicateCategorySlugError from exc
    except asyncpg.ForeignKeyViolationError as exc:
        raise ParentCategoryNotFoundError from exc

    if row is None:
        raise CategoryNotFoundError

    return category_from_record(row)


async def delete_category(pool: asyncpg.Pool, category_id: UUID) -> None:
    try:
        command_status = cast(
            str, await pool.execute("DELETE FROM categories WHERE id = $1", category_id)
        )
    except asyncpg.ForeignKeyViolationError as exc:
        raise CategoryDeleteConflictError from exc

    if rows_affected(command_status) == 0:
        raise CategoryNotFoundError


async def list_active_categories(
    pool: asyncpg.Pool,
    parent_id: UUID | None,
    root_only: bool,
    limit: int,
    cursor: tuple[int, str, UUID] | None,
) -> list[CategoryRead]:
    params: list[object] = [CategoryStatus.ACTIVE.value]
    conditions = ["status = $1::category_status"]

    if root_only:
        conditions.append("parent_id IS NULL")
    elif parent_id is not None:
        params.append(parent_id)
        conditions.append(f"parent_id = ${len(params)}")

    if cursor is not None:
        params.extend(cursor)
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
    return [category_from_record(row) for row in rows]


async def get_active_category(pool: asyncpg.Pool, category_id: UUID) -> CategoryRead:
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
        raise CategoryNotFoundError

    return category_from_record(row)
