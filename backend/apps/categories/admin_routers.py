from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response
from fastapi import status as http_status

from backend.apps.categories.admin_service import (
    create_category,
    delete_category,
    get_category,
    list_categories,
    update_category,
)
from backend.apps.categories.schemas import (
    CategoryCreate,
    CategoryListResponse,
    CategoryRead,
    CategoryUpdate,
)
from backend.apps.common.enums import CategoryStatus
from backend.config.database import DbPool

router = APIRouter(prefix="/categories", tags=["admin:categories"])


@router.post("", response_model=CategoryRead, status_code=http_status.HTTP_201_CREATED)
async def create_admin_category(
    payload: CategoryCreate,
    pool: DbPool,
) -> CategoryRead:
    return await create_category(pool, payload)


@router.get("", response_model=CategoryListResponse)
async def list_admin_categories(
    pool: DbPool,
    status_filter: Annotated[CategoryStatus | None, Query(alias="status")] = None,
    parent_id: UUID | None = None,
    root_only: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> CategoryListResponse:
    return await list_categories(
        pool=pool,
        status_filter=status_filter,
        parent_id=parent_id,
        root_only=root_only,
        page=page,
        limit=limit,
    )


@router.get("/{category_id}", response_model=CategoryRead)
async def read_admin_category(category_id: UUID, pool: DbPool) -> CategoryRead:
    return await get_category(pool, category_id)


@router.patch("/{category_id}", response_model=CategoryRead)
async def update_admin_category(
    category_id: UUID,
    payload: CategoryUpdate,
    pool: DbPool,
) -> CategoryRead:
    return await update_category(pool, category_id, payload)


@router.delete("/{category_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_admin_category(category_id: UUID, pool: DbPool) -> Response:
    await delete_category(pool, category_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
