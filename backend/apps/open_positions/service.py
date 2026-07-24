from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg

from backend.apps.common.enums import EmploymentType, LanguageCode
from backend.apps.common.exceptions import InvalidCursorError
from backend.apps.common.localization import required_localized_text
from backend.apps.common.pagination import (
    CursorPage,
    decode_cursor,
    encode_cursor,
)
from backend.apps.open_positions import repository
from backend.apps.open_positions.exceptions import OpenPositionNotFoundError
from backend.apps.open_positions.schemas import OpenPositionRead, PublicOpenPositionRead

PublicOpenPositionNotFoundError = OpenPositionNotFoundError


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
    parsed_cursor: OpenPositionCursor | None = None
    if cursor is not None:
        parsed_cursor = _parse_open_position_cursor(cursor)
    open_positions = await repository.list_active_open_positions(
        pool,
        employment_type,
        limit,
        (parsed_cursor.created_at, parsed_cursor.id) if parsed_cursor is not None else None,
    )
    next_cursor = (
        _open_position_cursor(open_positions[limit - 1]) if len(open_positions) > limit else None
    )
    return CursorPage(
        items=[_public_open_position(item, language) for item in open_positions[:limit]],
        limit=limit,
        next_cursor=next_cursor,
    )


async def get_public_open_position(
    pool: asyncpg.Pool, language: LanguageCode, open_position_id: UUID
) -> PublicOpenPositionRead:
    open_position = await repository.get_active_open_position(pool, open_position_id)
    return _public_open_position(open_position, language)


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
