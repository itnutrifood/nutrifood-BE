from typing import Annotated, NoReturn
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from backend.apps.common.enums import EmploymentType
from backend.apps.common.localization import LocaleFromPath
from backend.apps.common.pagination import CursorPage, InvalidCursorError
from backend.apps.open_positions.schemas import PublicOpenPositionRead
from backend.apps.open_positions.service import (
    PublicOpenPositionNotFoundError,
    get_public_open_position,
)
from backend.apps.open_positions.service import (
    list_public_open_positions as list_public_open_positions_service,
)
from backend.config.database import get_pool

DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]
router = APIRouter(prefix="/open-positions", tags=["open-positions"])


def _raise_open_position_http_error(
    exc: InvalidCursorError | PublicOpenPositionNotFoundError,
) -> NoReturn:
    if isinstance(exc, InvalidCursorError):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid cursor",
        ) from exc
    raise HTTPException(
        status_code=http_status.HTTP_404_NOT_FOUND,
        detail="Open position not found",
    ) from exc


@router.get("", response_model=CursorPage[PublicOpenPositionRead])
async def list_public_open_positions(
    language: LocaleFromPath,
    pool: DbPool,
    employment_type: EmploymentType | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> CursorPage[PublicOpenPositionRead]:
    try:
        return await list_public_open_positions_service(
            pool, language, employment_type, limit, cursor
        )
    except InvalidCursorError as exc:
        _raise_open_position_http_error(exc)


@router.get("/{open_position_id}", response_model=PublicOpenPositionRead)
async def read_public_open_position(
    language: LocaleFromPath, open_position_id: UUID, pool: DbPool
) -> PublicOpenPositionRead:
    try:
        return await get_public_open_position(pool, language, open_position_id)
    except PublicOpenPositionNotFoundError as exc:
        _raise_open_position_http_error(exc)
