from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

import asyncpg

from backend.apps.admin.testimonials import (
    TESTIMONIAL_COLUMNS,
    TestimonialRead,
    _testimonial_from_record,
)
from backend.apps.common.enums import TestimonialStatus
from backend.apps.common.pagination import (
    CursorPage,
    InvalidCursorError,
    decode_cursor,
    encode_cursor,
)
from backend.apps.testimonials.schemas import PublicTestimonialRead


class PublicTestimonialNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class TestimonialCursor:
    sort_order: int
    created_at: datetime
    id: UUID


def _parse_testimonial_cursor(cursor: str) -> TestimonialCursor:
    payload = decode_cursor(cursor)
    sort_order = payload.get("sort_order")
    created_at = payload.get("created_at")
    testimonial_id = payload.get("id")

    if isinstance(sort_order, bool) or not isinstance(sort_order, int):
        raise InvalidCursorError("Invalid testimonial cursor")
    if not isinstance(created_at, str) or not created_at:
        raise InvalidCursorError("Invalid testimonial cursor")
    if not isinstance(testimonial_id, str):
        raise InvalidCursorError("Invalid testimonial cursor")

    try:
        parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        parsed_testimonial_id = UUID(testimonial_id)
    except ValueError as exc:
        raise InvalidCursorError("Invalid testimonial cursor") from exc

    if parsed_created_at.tzinfo is None:
        raise InvalidCursorError("Invalid testimonial cursor")

    return TestimonialCursor(
        sort_order=sort_order,
        created_at=parsed_created_at,
        id=parsed_testimonial_id,
    )


def _testimonial_cursor(testimonial: TestimonialRead) -> str:
    return encode_cursor(
        {
            "sort_order": testimonial.sort_order,
            "created_at": testimonial.created_at,
            "id": testimonial.id,
        }
    )


async def list_public_testimonials(
    pool: asyncpg.Pool,
    limit: int,
    cursor: str | None,
) -> CursorPage[PublicTestimonialRead]:
    params: list[object] = [TestimonialStatus.ACTIVE.value]
    cursor_condition = ""
    if cursor is not None:
        testimonial_cursor = _parse_testimonial_cursor(cursor)
        params.extend(
            [
                testimonial_cursor.sort_order,
                testimonial_cursor.created_at,
                testimonial_cursor.id,
            ]
        )
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
    testimonials = [_testimonial_from_record(row) for row in rows[:limit]]
    next_cursor = _testimonial_cursor(testimonials[-1]) if len(rows) > limit else None
    return CursorPage(
        items=[_public_testimonial(testimonial) for testimonial in testimonials],
        limit=limit,
        next_cursor=next_cursor,
    )


async def get_public_testimonial(
    pool: asyncpg.Pool,
    testimonial_id: UUID,
) -> PublicTestimonialRead:
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
        raise PublicTestimonialNotFoundError
    return _public_testimonial(_testimonial_from_record(row))


def _public_testimonial(testimonial: TestimonialRead) -> PublicTestimonialRead:
    return PublicTestimonialRead(
        id=testimonial.id,
        first_name=testimonial.first_name,
        last_name=testimonial.last_name,
        author_title=testimonial.author_title,
        photo_url=testimonial.photo_url,
        review=testimonial.review,
        rating=testimonial.rating,
        sort_order=testimonial.sort_order,
        created_at=testimonial.created_at,
        updated_at=testimonial.updated_at,
    )
