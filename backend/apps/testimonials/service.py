from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg

from backend.apps.common.exceptions import InvalidCursorError
from backend.apps.common.pagination import (
    CursorPage,
    decode_cursor,
    encode_cursor,
)
from backend.apps.testimonials import repository
from backend.apps.testimonials.exceptions import TestimonialNotFoundError
from backend.apps.testimonials.schemas import PublicTestimonialRead, TestimonialRead

PublicTestimonialNotFoundError = TestimonialNotFoundError


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
    parsed_cursor: TestimonialCursor | None = None
    if cursor is not None:
        parsed_cursor = _parse_testimonial_cursor(cursor)

    testimonials = await repository.list_active_testimonials(
        pool,
        limit,
        (
            parsed_cursor.sort_order,
            parsed_cursor.created_at,
            parsed_cursor.id,
        )
        if parsed_cursor is not None
        else None,
    )
    next_cursor = (
        _testimonial_cursor(testimonials[limit - 1]) if len(testimonials) > limit else None
    )
    return CursorPage(
        items=[_public_testimonial(testimonial) for testimonial in testimonials[:limit]],
        limit=limit,
        next_cursor=next_cursor,
    )


async def get_public_testimonial(
    pool: asyncpg.Pool,
    testimonial_id: UUID,
) -> PublicTestimonialRead:
    testimonial = await repository.get_active_testimonial(pool, testimonial_id)
    return _public_testimonial(testimonial)


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
