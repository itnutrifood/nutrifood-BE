from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from backend.apps.categories.schemas import PublicCategoryRead
from backend.apps.categories.service import get_public_category
from backend.apps.categories.service import (
    list_public_categories as list_public_categories_service,
)
from backend.apps.common.localization import LocaleFromPath
from backend.apps.common.pagination import CursorPage
from backend.config.database import DbPool

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=CursorPage[PublicCategoryRead])
async def list_public_categories(
    language: LocaleFromPath,
    pool: DbPool,
    parent_id: UUID | None = None,
    root_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> CursorPage[PublicCategoryRead]:
    return await list_public_categories_service(
        pool=pool,
        language=language,
        parent_id=parent_id,
        root_only=root_only,
        limit=limit,
        cursor=cursor,
    )


@router.get("/{category_id}", response_model=PublicCategoryRead)
async def read_public_category(
    language: LocaleFromPath,
    category_id: UUID,
    pool: DbPool,
) -> PublicCategoryRead:
    return await get_public_category(pool, language, category_id)
