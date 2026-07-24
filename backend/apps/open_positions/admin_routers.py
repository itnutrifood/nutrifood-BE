from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response
from fastapi import status as http_status

from backend.apps.common.enums import EmploymentType, OpenPositionStatus
from backend.apps.open_positions.admin_service import (
    create_open_position,
    delete_open_position,
    get_open_position,
    list_open_positions,
    update_open_position,
)
from backend.apps.open_positions.schemas import (
    OpenPositionCreate,
    OpenPositionListResponse,
    OpenPositionRead,
    OpenPositionUpdate,
)
from backend.config.database import DbPool

router = APIRouter(prefix="/open-positions", tags=["admin:open-positions"])


@router.post("", response_model=OpenPositionRead, status_code=http_status.HTTP_201_CREATED)
async def create_admin_open_position(
    payload: OpenPositionCreate,
    pool: DbPool,
) -> OpenPositionRead:
    return await create_open_position(pool, payload)


@router.get("", response_model=OpenPositionListResponse)
async def list_admin_open_positions(
    pool: DbPool,
    status_filter: Annotated[OpenPositionStatus | None, Query(alias="status")] = None,
    employment_type_filter: Annotated[EmploymentType | None, Query(alias="employment_type")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> OpenPositionListResponse:
    return await list_open_positions(
        pool,
        status_filter,
        employment_type_filter,
        page,
        limit,
    )


@router.get("/{open_position_id}", response_model=OpenPositionRead)
async def read_admin_open_position(
    open_position_id: UUID,
    pool: DbPool,
) -> OpenPositionRead:
    return await get_open_position(pool, open_position_id)


@router.patch("/{open_position_id}", response_model=OpenPositionRead)
async def update_admin_open_position(
    open_position_id: UUID,
    payload: OpenPositionUpdate,
    pool: DbPool,
) -> OpenPositionRead:
    return await update_open_position(pool, open_position_id, payload)


@router.delete("/{open_position_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_admin_open_position(open_position_id: UUID, pool: DbPool) -> Response:
    await delete_open_position(pool, open_position_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
