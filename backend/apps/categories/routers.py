from typing import Annotated, NoReturn
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from backend.apps.categories.schemas import PublicCategoryRead
from backend.apps.categories.service import (
    CategoryFilterConflictError,
    PublicCategoryNotFoundError,
    get_public_category,
)
from backend.apps.categories.service import (
    list_public_categories as list_public_categories_service,
)
from backend.apps.common.localization import LocaleFromPath
from backend.apps.common.pagination import CursorPage, InvalidCursorError
from backend.config.database import get_pool

DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]

router = APIRouter(prefix="/categories", tags=["categories"])


def _raise_category_http_error(
    exc: InvalidCursorError | CategoryFilterConflictError | PublicCategoryNotFoundError,
) -> NoReturn:
    if isinstance(exc, InvalidCursorError):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid cursor",
        ) from exc
    if isinstance(exc, CategoryFilterConflictError):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    raise HTTPException(
        status_code=http_status.HTTP_404_NOT_FOUND,
        detail="Category not found",
    ) from exc


@router.get("", response_model=CursorPage[PublicCategoryRead])
async def list_public_categories(
    language: LocaleFromPath,
    pool: DbPool,
    parent_id: UUID | None = None,
    root_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> CursorPage[PublicCategoryRead]:
    try:
        return await list_public_categories_service(
            pool=pool,
            language=language,
            parent_id=parent_id,
            root_only=root_only,
            limit=limit,
            cursor=cursor,
        )
    except (InvalidCursorError, CategoryFilterConflictError) as exc:
        _raise_category_http_error(exc)


@router.get("/{category_id}", response_model=PublicCategoryRead)
async def read_public_category(
    language: LocaleFromPath,
    category_id: UUID,
    pool: DbPool,
) -> PublicCategoryRead:
    try:
        return await get_public_category(pool, language, category_id)
    except PublicCategoryNotFoundError as exc:
        _raise_category_http_error(exc)
