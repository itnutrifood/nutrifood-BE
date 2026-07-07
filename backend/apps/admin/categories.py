import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Annotated, Any, Self, cast
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import status as http_status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_serializer,
    model_validator,
)

from backend.apps.common.enums import CategoryStatus, LanguageCode
from backend.apps.common.pagination import Page, page_count, page_offset
from backend.config.database import get_pool

CategorySlug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]
SortOrder = Annotated[int, Field(ge=0, le=2_147_483_647)]
DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]

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


class LocalizedName(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    hy_am: str = Field(alias="HY-AM", min_length=1, max_length=255)
    en_us: str = Field(alias="EN-US", min_length=1, max_length=255)
    ru_ru: str = Field(alias="RU-RU", min_length=1, max_length=255)

    def to_db(self) -> dict[str, str]:
        return {
            LanguageCode.HY_AM.value: self.hy_am,
            LanguageCode.EN_US.value: self.en_us,
            LanguageCode.RU_RU.value: self.ru_ru,
        }

    @model_serializer(mode="plain")
    def serialize_model(self) -> dict[str, str]:
        return self.to_db()


class LocalizedDescription(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    hy_am: str | None = Field(default=None, alias="HY-AM", min_length=1)
    en_us: str | None = Field(default=None, alias="EN-US", min_length=1)
    ru_ru: str | None = Field(default=None, alias="RU-RU", min_length=1)

    def to_db(self) -> dict[str, str]:
        values = {
            LanguageCode.HY_AM.value: self.hy_am,
            LanguageCode.EN_US.value: self.en_us,
            LanguageCode.RU_RU.value: self.ru_ru,
        }
        return {language: value for language, value in values.items() if value is not None}

    @model_serializer(mode="plain")
    def serialize_model(self) -> dict[str, str]:
        return self.to_db()


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_id: UUID | None = None
    slug: CategorySlug
    name: LocalizedName
    description: LocalizedDescription = Field(default_factory=LocalizedDescription)
    status: CategoryStatus = CategoryStatus.ACTIVE
    sort_order: SortOrder = 0


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_id: UUID | None = None
    slug: CategorySlug | None = None
    name: LocalizedName | None = None
    description: LocalizedDescription | None = None
    status: CategoryStatus | None = None
    sort_order: SortOrder | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")

        nullable_fields = {"parent_id"}
        for field_name in self.model_fields_set - nullable_fields:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")

        return self


class CategoryRead(BaseModel):
    id: UUID
    parent_id: UUID | None
    slug: str
    name: LocalizedName
    description: LocalizedDescription
    status: CategoryStatus
    sort_order: int
    created_at: datetime
    updated_at: datetime


class CategoryListResponse(Page[CategoryRead]):
    pass


class CategoryNotFoundError(Exception):
    pass


class ParentCategoryNotFoundError(Exception):
    pass


class DuplicateCategorySlugError(Exception):
    pass


class CategoryHierarchyError(Exception):
    pass


class CategoryDeleteConflictError(Exception):
    pass


router = APIRouter(prefix="/categories", tags=["admin:categories"])


def _json_object(value: object) -> dict[str, object]:
    if isinstance(value, str):
        loaded_value = json.loads(value)
    elif isinstance(value, Mapping):
        loaded_value = dict(value)
    else:
        raise ValueError("Expected a JSON object")

    if not isinstance(loaded_value, dict):
        raise ValueError("Expected a JSON object")

    return cast(dict[str, object], loaded_value)


def _category_from_record(record: Mapping[str, object]) -> CategoryRead:
    return CategoryRead(
        id=cast(UUID, record["id"]),
        parent_id=cast(UUID | None, record["parent_id"]),
        slug=cast(str, record["slug"]),
        name=LocalizedName.model_validate(_json_object(record["name"])),
        description=LocalizedDescription.model_validate(_json_object(record["description"])),
        status=CategoryStatus(cast(str, record["status"])),
        sort_order=cast(int, record["sort_order"]),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


def _rows_affected(command_status: str) -> int:
    try:
        return int(command_status.rsplit(maxsplit=1)[-1])
    except (IndexError, ValueError):
        return 0


async def _category_exists(pool: asyncpg.Pool, category_id: UUID) -> bool:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            "SELECT EXISTS(SELECT 1 FROM categories WHERE id = $1) AS exists", category_id
        ),
    )
    return bool(row and row["exists"])


async def _ensure_parent_exists(pool: asyncpg.Pool, parent_id: UUID) -> None:
    if not await _category_exists(pool, parent_id):
        raise ParentCategoryNotFoundError


async def _is_descendant(pool: asyncpg.Pool, category_id: UUID, parent_id: UUID) -> bool:
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


async def _validate_parent_for_update(
    pool: asyncpg.Pool,
    category_id: UUID,
    parent_id: UUID | None,
) -> None:
    if parent_id is None:
        return

    if parent_id == category_id:
        raise CategoryHierarchyError("A category cannot be its own parent")

    await _ensure_parent_exists(pool, parent_id)

    if await _is_descendant(pool, category_id, parent_id):
        raise CategoryHierarchyError("A category cannot be moved below one of its descendants")


async def create_category(pool: asyncpg.Pool, payload: CategoryCreate) -> CategoryRead:
    if payload.parent_id is not None:
        await _ensure_parent_exists(pool, payload.parent_id)

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

    return _category_from_record(row)


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

    return _category_from_record(row)


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

    offset = page_offset(page, limit)
    params.extend([limit, offset])
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
        items=[_category_from_record(row) for row in rows],
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
    if not await _category_exists(pool, category_id):
        raise CategoryNotFoundError

    assignments: list[str] = []
    params: list[Any] = []

    if "parent_id" in payload.model_fields_set:
        await _validate_parent_for_update(pool, category_id, payload.parent_id)
        params.append(payload.parent_id)
        assignments.append(f"parent_id = ${len(params)}")

    if "slug" in payload.model_fields_set:
        params.append(payload.slug)
        assignments.append(f"slug = ${len(params)}")

    if "name" in payload.model_fields_set:
        if payload.name is None:
            raise ValueError("name cannot be null")
        params.append(json.dumps(payload.name.to_db()))
        assignments.append(f"name = ${len(params)}::jsonb")

    if "description" in payload.model_fields_set:
        if payload.description is None:
            raise ValueError("description cannot be null")
        params.append(json.dumps(payload.description.to_db()))
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

    return _category_from_record(row)


async def delete_category(pool: asyncpg.Pool, category_id: UUID) -> None:
    try:
        command_status = cast(
            str, await pool.execute("DELETE FROM categories WHERE id = $1", category_id)
        )
    except asyncpg.ForeignKeyViolationError as exc:
        raise CategoryDeleteConflictError from exc

    if _rows_affected(command_status) == 0:
        raise CategoryNotFoundError


def _raise_category_http_error(exc: Exception) -> None:
    if isinstance(exc, CategoryNotFoundError):
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        ) from exc
    if isinstance(exc, ParentCategoryNotFoundError):
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Parent category not found",
        ) from exc
    if isinstance(exc, DuplicateCategorySlugError):
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Category slug already exists",
        ) from exc
    if isinstance(exc, CategoryHierarchyError):
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if isinstance(exc, CategoryDeleteConflictError):
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Category has child categories or linked records",
        ) from exc

    raise exc


@router.post(
    "",
    response_model=CategoryRead,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_admin_category(
    payload: CategoryCreate,
    pool: DbPool,
) -> CategoryRead:
    try:
        return await create_category(pool, payload)
    except Exception as exc:
        _raise_category_http_error(exc)
        raise


@router.get("", response_model=CategoryListResponse)
async def list_admin_categories(
    pool: DbPool,
    status_filter: Annotated[CategoryStatus | None, Query(alias="status")] = None,
    parent_id: UUID | None = None,
    root_only: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> CategoryListResponse:
    if root_only and parent_id is not None:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="root_only and parent_id cannot be used together",
        )

    return await list_categories(
        pool=pool,
        status_filter=status_filter,
        parent_id=parent_id,
        root_only=root_only,
        page=page,
        limit=limit,
    )


@router.get("/{category_id}", response_model=CategoryRead)
async def read_admin_category(
    category_id: UUID,
    pool: DbPool,
) -> CategoryRead:
    try:
        return await get_category(pool, category_id)
    except Exception as exc:
        _raise_category_http_error(exc)
        raise


@router.patch("/{category_id}", response_model=CategoryRead)
async def update_admin_category(
    category_id: UUID,
    payload: CategoryUpdate,
    pool: DbPool,
) -> CategoryRead:
    try:
        return await update_category(pool, category_id, payload)
    except Exception as exc:
        _raise_category_http_error(exc)
        raise


@router.delete("/{category_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_admin_category(
    category_id: UUID,
    pool: DbPool,
) -> Response:
    try:
        await delete_category(pool, category_id)
    except Exception as exc:
        _raise_category_http_error(exc)
        raise

    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
