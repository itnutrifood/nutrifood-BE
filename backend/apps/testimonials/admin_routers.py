from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response
from fastapi import status as http_status

from backend.apps.common.enums import TestimonialStatus
from backend.apps.testimonials.admin_service import (
    create_testimonial,
    delete_testimonial,
    get_testimonial,
    list_testimonials,
    update_testimonial,
)
from backend.apps.testimonials.schemas import (
    TestimonialCreate,
    TestimonialListResponse,
    TestimonialRead,
    TestimonialUpdate,
)
from backend.config.database import DbPool

router = APIRouter(prefix="/testimonials", tags=["admin:testimonials"])


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
async def read_admin_testimonial(
    testimonial_id: UUID,
    pool: DbPool,
) -> TestimonialRead:
    return await get_testimonial(pool, testimonial_id)


@router.patch("/{testimonial_id}", response_model=TestimonialRead)
async def update_admin_testimonial(
    testimonial_id: UUID,
    payload: TestimonialUpdate,
    pool: DbPool,
) -> TestimonialRead:
    return await update_testimonial(pool, testimonial_id, payload)


@router.delete("/{testimonial_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_admin_testimonial(testimonial_id: UUID, pool: DbPool) -> Response:
    await delete_testimonial(pool, testimonial_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
