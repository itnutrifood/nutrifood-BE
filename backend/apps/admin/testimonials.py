from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Annotated, Any, NoReturn, Self, cast
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.apps.common.enums import TestimonialStatus
from backend.apps.common.pagination import Page, page_count, page_offset
from backend.config.database import get_pool

PersonName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=150),
]
AuthorTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
PhotoUrl = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2048),
]
Review = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=5000),
]
Rating = Annotated[int, Field(ge=1, le=5)]
SortOrder = Annotated[int, Field(ge=0, le=2_147_483_647)]
DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]

TESTIMONIAL_COLUMNS = """
    id,
    first_name,
    last_name,
    author_title,
    photo_url,
    review,
    rating,
    status::text AS status,
    sort_order,
    created_at,
    updated_at
"""


class TestimonialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: PersonName
    last_name: PersonName
    author_title: AuthorTitle
    photo_url: PhotoUrl | None = None
    review: Review
    rating: Rating
    status: TestimonialStatus = TestimonialStatus.ACTIVE
    sort_order: SortOrder = 0


class TestimonialUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: PersonName | None = None
    last_name: PersonName | None = None
    author_title: AuthorTitle | None = None
    photo_url: PhotoUrl | None = None
    review: Review | None = None
    rating: Rating | None = None
    status: TestimonialStatus | None = None
    sort_order: SortOrder | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")

        nullable_fields = {"photo_url"}
        for field_name in self.model_fields_set - nullable_fields:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")

        return self


class TestimonialRead(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    author_title: str
    photo_url: str | None
    review: str
    rating: int
    status: TestimonialStatus
    sort_order: int
    created_at: datetime
    updated_at: datetime


class TestimonialListResponse(Page[TestimonialRead]):
    pass


class TestimonialNotFoundError(Exception):
    pass


router = APIRouter(prefix="/testimonials", tags=["admin:testimonials"])


def _testimonial_from_record(record: Mapping[str, object]) -> TestimonialRead:
    return TestimonialRead(
        id=cast(UUID, record["id"]),
        first_name=cast(str, record["first_name"]),
        last_name=cast(str, record["last_name"]),
        author_title=cast(str, record["author_title"]),
        photo_url=cast(str | None, record["photo_url"]),
        review=cast(str, record["review"]),
        rating=cast(int, record["rating"]),
        status=TestimonialStatus(cast(str, record["status"])),
        sort_order=cast(int, record["sort_order"]),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


async def create_testimonial(
    pool: asyncpg.Pool,
    payload: TestimonialCreate,
) -> TestimonialRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            INSERT INTO testimonials (
                first_name,
                last_name,
                author_title,
                photo_url,
                review,
                rating,
                status,
                sort_order
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::testimonial_status, $8)
            RETURNING {TESTIMONIAL_COLUMNS}
            """,
            payload.first_name,
            payload.last_name,
            payload.author_title,
            payload.photo_url,
            payload.review,
            payload.rating,
            payload.status.value,
            payload.sort_order,
        ),
    )
    if row is None:
        raise RuntimeError("Testimonial insert did not return a row")

    return _testimonial_from_record(row)


async def get_testimonial(pool: asyncpg.Pool, testimonial_id: UUID) -> TestimonialRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"SELECT {TESTIMONIAL_COLUMNS} FROM testimonials WHERE id = $1",
            testimonial_id,
        ),
    )
    if row is None:
        raise TestimonialNotFoundError
    return _testimonial_from_record(row)


async def list_testimonials(
    pool: asyncpg.Pool,
    status_filter: TestimonialStatus | None,
    page: int,
    limit: int,
) -> TestimonialListResponse:
    params: list[object] = []
    where_clause = ""
    if status_filter is not None:
        params.append(status_filter.value)
        where_clause = "WHERE status = $1::testimonial_status"

    count_row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"SELECT count(*) AS total FROM testimonials {where_clause}",
            *params,
        ),
    )
    total = cast(int, count_row["total"]) if count_row is not None else 0

    params.extend([limit, page_offset(page, limit)])
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {TESTIMONIAL_COLUMNS}
            FROM testimonials
            {where_clause}
            ORDER BY sort_order, created_at DESC, id DESC
            LIMIT ${len(params) - 1}
            OFFSET ${len(params)}
            """,
            *params,
        ),
    )
    return TestimonialListResponse(
        items=[_testimonial_from_record(row) for row in rows],
        total=total,
        page=page,
        limit=limit,
        total_pages=page_count(total, limit),
    )


async def update_testimonial(
    pool: asyncpg.Pool,
    testimonial_id: UUID,
    payload: TestimonialUpdate,
) -> TestimonialRead:
    assignments: list[str] = []
    params: list[Any] = []

    scalar_fields = (
        "first_name",
        "last_name",
        "author_title",
        "photo_url",
        "review",
        "rating",
        "sort_order",
    )
    for field_name in scalar_fields:
        if field_name in payload.model_fields_set:
            params.append(getattr(payload, field_name))
            assignments.append(f"{field_name} = ${len(params)}")
    if "status" in payload.model_fields_set:
        params.append(cast(TestimonialStatus, payload.status).value)
        assignments.append(f"status = ${len(params)}::testimonial_status")

    params.append(testimonial_id)
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            UPDATE testimonials
            SET {", ".join(assignments)}
            WHERE id = ${len(params)}
            RETURNING {TESTIMONIAL_COLUMNS}
            """,
            *params,
        ),
    )
    if row is None:
        raise TestimonialNotFoundError
    return _testimonial_from_record(row)


async def delete_testimonial(pool: asyncpg.Pool, testimonial_id: UUID) -> None:
    result = cast(
        str,
        await pool.execute("DELETE FROM testimonials WHERE id = $1", testimonial_id),
    )
    try:
        rows_affected = int(result.rsplit(maxsplit=1)[-1])
    except (IndexError, ValueError):
        rows_affected = 0
    if rows_affected == 0:
        raise TestimonialNotFoundError


def _raise_not_found(exc: TestimonialNotFoundError) -> NoReturn:
    raise HTTPException(
        status_code=http_status.HTTP_404_NOT_FOUND,
        detail="Testimonial not found",
    ) from exc


@router.post("", response_model=TestimonialRead, status_code=http_status.HTTP_201_CREATED)
async def create_admin_testimonial(
    payload: TestimonialCreate,
    pool: DbPool,
) -> TestimonialRead:
    return await create_testimonial(pool, payload)


@router.get("", response_model=TestimonialListResponse)
async def list_admin_testimonials(
    pool: DbPool,
    status_filter: Annotated[TestimonialStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> TestimonialListResponse:
    return await list_testimonials(pool, status_filter, page, limit)


@router.get("/{testimonial_id}", response_model=TestimonialRead)
async def read_admin_testimonial(testimonial_id: UUID, pool: DbPool) -> TestimonialRead:
    try:
        return await get_testimonial(pool, testimonial_id)
    except TestimonialNotFoundError as exc:
        _raise_not_found(exc)


@router.patch("/{testimonial_id}", response_model=TestimonialRead)
async def update_admin_testimonial(
    testimonial_id: UUID,
    payload: TestimonialUpdate,
    pool: DbPool,
) -> TestimonialRead:
    try:
        return await update_testimonial(pool, testimonial_id, payload)
    except TestimonialNotFoundError as exc:
        _raise_not_found(exc)


@router.delete("/{testimonial_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_admin_testimonial(testimonial_id: UUID, pool: DbPool) -> Response:
    try:
        await delete_testimonial(pool, testimonial_id)
    except TestimonialNotFoundError as exc:
        _raise_not_found(exc)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
