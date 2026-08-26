from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from backend.apps.common.localization import LocaleFromPath
from backend.apps.common.pagination import CursorPage
from backend.apps.products.schemas import PublicProductRead
from backend.apps.products.service import get_public_product
from backend.apps.products.service import (
    list_public_products as list_public_products_service,
)
from backend.config.database import DbPool

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=CursorPage[PublicProductRead])
async def list_public_products(
    language: LocaleFromPath,
    pool: DbPool,
    category_id: UUID | None = None,
    search: Annotated[
        str | None,
        Query(min_length=1, max_length=100, pattern=r".*\S.*"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> CursorPage[PublicProductRead]:
    return await list_public_products_service(
        pool=pool,
        language=language,
        category_id=category_id,
        search=search,
        limit=limit,
        cursor=cursor,
    )


@router.get("/{product_id}", response_model=PublicProductRead)
async def read_public_product(
    language: LocaleFromPath,
    product_id: UUID,
    pool: DbPool,
) -> PublicProductRead:
    return await get_public_product(pool, language, product_id)
