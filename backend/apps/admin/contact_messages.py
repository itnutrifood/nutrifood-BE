from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict

from backend.apps.common.enums import ContactMessageStatus
from backend.apps.contacts.schemas import ContactMessageRead
from backend.apps.contacts.service import (
    ContactMessageListResponse,
    ContactMessageNotFoundError,
    get_contact_message,
    list_contact_messages,
    update_contact_message_status,
)
from backend.config.database import get_pool

DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]


class ContactMessageStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ContactMessageStatus


router = APIRouter(prefix="/contact-messages", tags=["admin:contact-messages"])


def _contact_message_not_found(exc: ContactMessageNotFoundError) -> HTTPException:
    return HTTPException(
        status_code=http_status.HTTP_404_NOT_FOUND,
        detail="Contact message not found",
    )


@router.get("", response_model=ContactMessageListResponse)
async def list_admin_contact_messages(
    pool: DbPool,
    status_filter: Annotated[ContactMessageStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ContactMessageListResponse:
    return await list_contact_messages(pool, status_filter, page, limit)


@router.get("/{message_id}", response_model=ContactMessageRead)
async def read_admin_contact_message(message_id: UUID, pool: DbPool) -> ContactMessageRead:
    try:
        return await get_contact_message(pool, message_id)
    except ContactMessageNotFoundError as exc:
        raise _contact_message_not_found(exc) from exc


@router.patch("/{message_id}", response_model=ContactMessageRead)
async def update_admin_contact_message_status(
    message_id: UUID,
    payload: ContactMessageStatusUpdate,
    pool: DbPool,
) -> ContactMessageRead:
    try:
        return await update_contact_message_status(pool, message_id, payload.status)
    except ContactMessageNotFoundError as exc:
        raise _contact_message_not_found(exc) from exc
