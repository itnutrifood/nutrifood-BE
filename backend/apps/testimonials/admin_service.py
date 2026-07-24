from uuid import UUID

import asyncpg

from backend.apps.common.enums import TestimonialStatus
from backend.apps.testimonials import repository
from backend.apps.testimonials.schemas import (
    TestimonialCreate,
    TestimonialListResponse,
    TestimonialRead,
    TestimonialUpdate,
)


async def create_testimonial(
    pool: asyncpg.Pool,
    payload: TestimonialCreate,
) -> TestimonialRead:
    return await repository.create_testimonial(pool, payload)


async def get_testimonial(pool: asyncpg.Pool, testimonial_id: UUID) -> TestimonialRead:
    return await repository.get_testimonial(pool, testimonial_id)


async def list_testimonials(
    pool: asyncpg.Pool,
    status_filter: TestimonialStatus | None,
    page: int,
    limit: int,
) -> TestimonialListResponse:
    return await repository.list_testimonials(pool, status_filter, page, limit)


async def update_testimonial(
    pool: asyncpg.Pool,
    testimonial_id: UUID,
    payload: TestimonialUpdate,
) -> TestimonialRead:
    return await repository.update_testimonial(pool, testimonial_id, payload)


async def delete_testimonial(pool: asyncpg.Pool, testimonial_id: UUID) -> None:
    await repository.delete_testimonial(pool, testimonial_id)
