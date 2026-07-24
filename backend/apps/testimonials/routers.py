from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from backend.apps.common.pagination import CursorPage
from backend.apps.testimonials.schemas import PublicTestimonialRead
from backend.apps.testimonials.service import (
    get_public_testimonial,
)
from backend.apps.testimonials.service import (
    list_public_testimonials as list_public_testimonials_service,
)
from backend.config.database import DbPool

router = APIRouter(prefix="/testimonials", tags=["testimonials"])


@router.get("", response_model=CursorPage[PublicTestimonialRead])
async def list_public_testimonials(
    pool: DbPool,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> CursorPage[PublicTestimonialRead]:
    return await list_public_testimonials_service(pool, limit, cursor)


@router.get("/{testimonial_id}", response_model=PublicTestimonialRead)
async def read_public_testimonial(
    testimonial_id: UUID,
    pool: DbPool,
) -> PublicTestimonialRead:
    return await get_public_testimonial(pool, testimonial_id)
