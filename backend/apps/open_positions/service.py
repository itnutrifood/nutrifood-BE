from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

import asyncpg

from backend.apps.admin.open_positions import (
    OPEN_POSITION_COLUMNS,
    OpenPositionRead,
    _open_position_from_record,
)
from backend.apps.common.enums import EmploymentType, LanguageCode, OpenPositionStatus
from backend.apps.common.localization import required_localized_text
from backend.apps.common.pagination import (
    CursorPage,
    InvalidCursorError,
    decode_cursor,
    encode_cursor,
)
from backend.apps.open_positions.schemas import PublicOpenPositionRead


class PublicOpenPositionNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class OpenPositionCursor:
    created_at: datetime
    id: UUID


def _parse_open_position_cursor(cursor: str) -> OpenPositionCursor:
    payload = decode_cursor(cursor)
    created_at = payload.get("created_at")
    open_position_id = payload.get("id")
    if not isinstance(created_at, str) or not created_at:
        raise InvalidCursorError("Invalid open position cursor")
    if not isinstance(open_position_id, str):
        raise InvalidCursorError("Invalid open position cursor")
    try:
        parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        parsed_id = UUID(open_position_id)
    except ValueError as exc:
        raise InvalidCursorError("Invalid open position cursor") from exc
    if parsed_created_at.tzinfo is None:
        raise InvalidCursorError("Invalid open position cursor")
    return OpenPositionCursor(created_at=parsed_created_at, id=parsed_id)


def _open_position_cursor(open_position: OpenPositionRead) -> str:
    return encode_cursor({"created_at": open_position.created_at, "id": open_position.id})


async def list_public_open_positions(
    pool: asyncpg.Pool,
    language: LanguageCode,
    employment_type: EmploymentType | None,
    limit: int,
    cursor: str | None,
) -> CursorPage[PublicOpenPositionRead]:
    params: list[object] = [OpenPositionStatus.ACTIVE.value]
    conditions = ["status = $1::open_position_status"]
    if employment_type is not None:
        params.append(employment_type.value)
        conditions.append(f"employment_type = ${len(params)}::employment_type")
    if cursor is not None:
        parsed_cursor = _parse_open_position_cursor(cursor)
        params.extend([parsed_cursor.created_at, parsed_cursor.id])
        conditions.append(f"(created_at, id) < (${len(params) - 1}, ${len(params)})")
    params.append(limit + 1)
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {OPEN_POSITION_COLUMNS}
            FROM open_positions
            WHERE {" AND ".join(conditions)}
            ORDER BY created_at DESC, id DESC
            LIMIT ${len(params)}
            """,
            *params,
        ),
    )
    open_positions = [_open_position_from_record(row) for row in rows[:limit]]
    next_cursor = _open_position_cursor(open_positions[-1]) if len(rows) > limit else None
    return CursorPage(
        items=[_public_open_position(item, language) for item in open_positions],
        limit=limit,
        next_cursor=next_cursor,
    )


async def get_public_open_position(
    pool: asyncpg.Pool, language: LanguageCode, open_position_id: UUID
) -> PublicOpenPositionRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {OPEN_POSITION_COLUMNS}
            FROM open_positions
            WHERE id = $1 AND status = $2::open_position_status
            """,
            open_position_id,
            OpenPositionStatus.ACTIVE.value,
        ),
    )
    if row is None:
        raise PublicOpenPositionNotFoundError
    return _public_open_position(_open_position_from_record(row), language)


def _public_open_position(
    open_position: OpenPositionRead, language: LanguageCode
) -> PublicOpenPositionRead:
    return PublicOpenPositionRead(
        id=open_position.id,
        title=required_localized_text(open_position.title.to_db(), language),
        employment_type=open_position.employment_type,
        description=required_localized_text(open_position.description.to_db(), language),
        position=required_localized_text(open_position.position.to_db(), language),
        city=required_localized_text(open_position.city.to_db(), language),
        created_at=open_position.created_at,
        updated_at=open_position.updated_at,
    )
