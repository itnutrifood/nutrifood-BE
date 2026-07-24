from uuid import UUID

import asyncpg

from backend.apps.common.enums import ContactMessageStatus
from backend.apps.contacts import repository
from backend.apps.contacts.exceptions import (
    ContactMessageNotFoundError as ContactMessageNotFoundError,
)
from backend.apps.contacts.schemas import (
    ContactMessageCreate,
    ContactMessageListResponse,
    ContactMessageRead,
)


async def create_contact_message(
    pool: asyncpg.Pool,
    payload: ContactMessageCreate,
) -> ContactMessageRead:
    return await repository.create_contact_message(pool, payload)


async def get_contact_message(pool: asyncpg.Pool, message_id: UUID) -> ContactMessageRead:
    return await repository.get_contact_message(pool, message_id)


async def list_contact_messages(
    pool: asyncpg.Pool,
    status_filter: ContactMessageStatus | None,
    page: int,
    limit: int,
) -> ContactMessageListResponse:
    return await repository.list_contact_messages(pool, status_filter, page, limit)


async def update_contact_message_status(
    pool: asyncpg.Pool,
    message_id: UUID,
    status: ContactMessageStatus,
) -> ContactMessageRead:
    return await repository.update_contact_message_status(pool, message_id, status)
