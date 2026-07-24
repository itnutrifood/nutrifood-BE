from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from backend.apps.common.enums import ContactMessageStatus
from backend.apps.contacts.schemas import (
    ContactMessageListResponse,
    ContactMessageRead,
    ContactMessageStatusUpdate,
)
from backend.apps.contacts.service import (
    get_contact_message,
    list_contact_messages,
    update_contact_message_status,
)
from backend.config.database import DbPool

router = APIRouter(prefix="/contact-messages", tags=["admin:contact-messages"])


@router.get("", response_model=ContactMessageListResponse)
async def list_admin_contact_messages(
    pool: DbPool,
    status_filter: Annotated[ContactMessageStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ContactMessageListResponse:
    return await list_contact_messages(pool, status_filter, page, limit)


@router.get("/{message_id}", response_model=ContactMessageRead)
async def read_admin_contact_message(
    message_id: UUID,
    pool: DbPool,
) -> ContactMessageRead:
    return await get_contact_message(pool, message_id)


@router.patch("/{message_id}", response_model=ContactMessageRead)
async def update_admin_contact_message_status(
    message_id: UUID,
    payload: ContactMessageStatusUpdate,
    pool: DbPool,
) -> ContactMessageRead:
    return await update_contact_message_status(pool, message_id, payload.status)
