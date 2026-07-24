from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from backend.apps.common.enums import EmploymentType
from backend.apps.common.localization import LocaleFromPath
from backend.apps.common.pagination import CursorPage
from backend.apps.open_positions.schemas import PublicOpenPositionRead
from backend.apps.open_positions.service import get_public_open_position
from backend.apps.open_positions.service import (
    list_public_open_positions as list_public_open_positions_service,
)
from backend.config.database import DbPool

router = APIRouter(prefix="/open-positions", tags=["open-positions"])


@router.get("", response_model=CursorPage[PublicOpenPositionRead])
async def list_public_open_positions(
    language: LocaleFromPath,
    pool: DbPool,
    employment_type: EmploymentType | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> CursorPage[PublicOpenPositionRead]:
    return await list_public_open_positions_service(pool, language, employment_type, limit, cursor)


@router.get("/{open_position_id}", response_model=PublicOpenPositionRead)
async def read_public_open_position(
    language: LocaleFromPath, open_position_id: UUID, pool: DbPool
) -> PublicOpenPositionRead:
    return await get_public_open_position(pool, language, open_position_id)
