from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response
from fastapi import status as http_status

from backend.apps.common.enums import FAQStatus
from backend.apps.faqs.admin_service import (
    create_faq,
    delete_faq,
    get_faq,
    list_faqs,
    update_faq,
)
from backend.apps.faqs.schemas import FAQCreate, FAQListResponse, FAQRead, FAQUpdate
from backend.config.database import DbPool

router = APIRouter(prefix="/faqs", tags=["admin:faqs"])


@router.post("", response_model=FAQRead, status_code=http_status.HTTP_201_CREATED)
async def create_admin_faq(payload: FAQCreate, pool: DbPool) -> FAQRead:
    return await create_faq(pool, payload)


@router.get("", response_model=FAQListResponse)
async def list_admin_faqs(
    pool: DbPool,
    status_filter: Annotated[FAQStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> FAQListResponse:
    return await list_faqs(pool, status_filter, page, limit)


@router.get("/{faq_id}", response_model=FAQRead)
async def read_admin_faq(faq_id: UUID, pool: DbPool) -> FAQRead:
    return await get_faq(pool, faq_id)


@router.patch("/{faq_id}", response_model=FAQRead)
async def update_admin_faq(
    faq_id: UUID,
    payload: FAQUpdate,
    pool: DbPool,
) -> FAQRead:
    return await update_faq(pool, faq_id, payload)


@router.delete("/{faq_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_admin_faq(faq_id: UUID, pool: DbPool) -> Response:
    await delete_faq(pool, faq_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
