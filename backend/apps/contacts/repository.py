from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

import asyncpg

from backend.apps.common.enums import ContactMessageStatus
from backend.apps.common.pagination import page_count, page_offset
from backend.apps.contacts.exceptions import ContactMessageNotFoundError
from backend.apps.contacts.schemas import (
    ContactMessageCreate,
    ContactMessageListResponse,
    ContactMessageRead,
)

CONTACT_MESSAGE_COLUMNS = """
    id,
    name,
    email,
    subject,
    message,
    status::text AS status,
    created_at,
    updated_at
"""


def contact_message_from_record(record: Mapping[str, object]) -> ContactMessageRead:
    return ContactMessageRead(
        id=cast(UUID, record["id"]),
        name=cast(str, record["name"]),
        email=cast(str, record["email"]),
        subject=cast(str, record["subject"]),
        message=cast(str, record["message"]),
        status=ContactMessageStatus(cast(str, record["status"])),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


async def create_contact_message(
    pool: asyncpg.Pool,
    payload: ContactMessageCreate,
) -> ContactMessageRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            INSERT INTO contact_messages (name, email, subject, message)
            VALUES ($1, $2, $3, $4)
            RETURNING {CONTACT_MESSAGE_COLUMNS}
            """,
            payload.name,
            str(payload.email).lower(),
            payload.subject,
            payload.message,
        ),
    )
    if row is None:
        raise RuntimeError("Contact message insert did not return a row")
    return contact_message_from_record(row)


async def get_contact_message(
    pool: asyncpg.Pool,
    message_id: UUID,
) -> ContactMessageRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {CONTACT_MESSAGE_COLUMNS}
            FROM contact_messages
            WHERE id = $1
            """,
            message_id,
        ),
    )
    if row is None:
        raise ContactMessageNotFoundError
    return contact_message_from_record(row)


async def list_contact_messages(
    pool: asyncpg.Pool,
    status_filter: ContactMessageStatus | None,
    page: int,
    limit: int,
) -> ContactMessageListResponse:
    params: list[object] = []
    where_clause = ""
    if status_filter is not None:
        params.append(status_filter.value)
        where_clause = "WHERE status = $1::contact_message_status"

    count_row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"SELECT count(*) AS total FROM contact_messages {where_clause}", *params
        ),
    )
    total = cast(int, count_row["total"]) if count_row is not None else 0

    params.extend([limit, page_offset(page, limit)])
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {CONTACT_MESSAGE_COLUMNS}
            FROM contact_messages
            {where_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT ${len(params) - 1}
            OFFSET ${len(params)}
            """,
            *params,
        ),
    )
    return ContactMessageListResponse(
        items=[contact_message_from_record(row) for row in rows],
        total=total,
        page=page,
        limit=limit,
        total_pages=page_count(total, limit),
    )


async def update_contact_message_status(
    pool: asyncpg.Pool,
    message_id: UUID,
    status: ContactMessageStatus,
) -> ContactMessageRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            UPDATE contact_messages
            SET status = $1::contact_message_status
            WHERE id = $2
            RETURNING {CONTACT_MESSAGE_COLUMNS}
            """,
            status.value,
            message_id,
        ),
    )
    if row is None:
        raise ContactMessageNotFoundError
    return contact_message_from_record(row)
