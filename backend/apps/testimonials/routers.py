from typing import Annotated, NoReturn
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from backend.apps.common.pagination import CursorPage, InvalidCursorError
from backend.apps.testimonials.schemas import PublicTestimonialRead
from backend.apps.testimonials.service import (
    PublicTestimonialNotFoundError,
    get_public_testimonial,
)
from backend.apps.testimonials.service import (
    list_public_testimonials as list_public_testimonials_service,
)
from backend.config.database import get_pool

DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]

router = APIRouter(prefix="/testimonials", tags=["testimonials"])


def _raise_testimonial_http_error(
    exc: InvalidCursorError | PublicTestimonialNotFoundError,
) -> NoReturn:
    if isinstance(exc, InvalidCursorError):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid cursor",
        ) from exc

    raise HTTPException(
        status_code=http_status.HTTP_404_NOT_FOUND,
        detail="Testimonial not found",
    ) from exc


@router.get("", response_model=CursorPage[PublicTestimonialRead])
async def list_public_testimonials(
    pool: DbPool,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> CursorPage[PublicTestimonialRead]:
    try:
        return await list_public_testimonials_service(pool, limit, cursor)
    except InvalidCursorError as exc:
        _raise_testimonial_http_error(exc)


@router.get("/{testimonial_id}", response_model=PublicTestimonialRead)
async def read_public_testimonial(
    testimonial_id: UUID,
    pool: DbPool,
) -> PublicTestimonialRead:
    try:
        return await get_public_testimonial(pool, testimonial_id)
    except PublicTestimonialNotFoundError as exc:
        _raise_testimonial_http_error(exc)
