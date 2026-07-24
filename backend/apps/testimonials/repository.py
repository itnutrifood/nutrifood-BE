from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import asyncpg

from backend.apps.common.db import rows_affected
from backend.apps.common.enums import TestimonialStatus
from backend.apps.common.pagination import page_count, page_offset
from backend.apps.testimonials.exceptions import TestimonialNotFoundError
from backend.apps.testimonials.schemas import (
    TestimonialCreate,
    TestimonialListResponse,
    TestimonialRead,
    TestimonialUpdate,
)

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


def testimonial_from_record(record: Mapping[str, object]) -> TestimonialRead:
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

    return testimonial_from_record(row)


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
    return testimonial_from_record(row)


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
        items=[testimonial_from_record(row) for row in rows],
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
    return testimonial_from_record(row)


async def delete_testimonial(pool: asyncpg.Pool, testimonial_id: UUID) -> None:
    result = cast(
        str,
        await pool.execute("DELETE FROM testimonials WHERE id = $1", testimonial_id),
    )
    if rows_affected(result) == 0:
        raise TestimonialNotFoundError


async def list_active_testimonials(
    pool: asyncpg.Pool,
    limit: int,
    cursor: tuple[int, datetime, UUID] | None,
) -> list[TestimonialRead]:
    params: list[object] = [TestimonialStatus.ACTIVE.value]
    cursor_condition = ""
    if cursor is not None:
        params.extend(cursor)
        cursor_condition = """
            AND (
                sort_order > $2
                OR (
                    sort_order = $2
                    AND (created_at, id) < ($3, $4)
                )
            )
        """

    params.append(limit + 1)
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {TESTIMONIAL_COLUMNS}
            FROM testimonials
            WHERE status = $1::testimonial_status
            {cursor_condition}
            ORDER BY sort_order, created_at DESC, id DESC
            LIMIT ${len(params)}
            """,
            *params,
        ),
    )
    return [testimonial_from_record(row) for row in rows]


async def get_active_testimonial(
    pool: asyncpg.Pool,
    testimonial_id: UUID,
) -> TestimonialRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {TESTIMONIAL_COLUMNS}
            FROM testimonials
            WHERE id = $1
                AND status = $2::testimonial_status
            """,
            testimonial_id,
            TestimonialStatus.ACTIVE.value,
        ),
    )
    if row is None:
        raise TestimonialNotFoundError
    return testimonial_from_record(row)
