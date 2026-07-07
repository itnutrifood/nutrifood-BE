from typing import Annotated, NoReturn
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from backend.apps.common.localization import LocaleFromPath
from backend.apps.common.pagination import CursorPage, InvalidCursorError
from backend.apps.products.schemas import PublicProductRead
from backend.apps.products.service import PublicProductNotFoundError, get_public_product
from backend.apps.products.service import list_public_products as list_public_products_service
from backend.config.database import get_pool

DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]

router = APIRouter(prefix="/products", tags=["products"])


def _raise_product_http_error(
    exc: InvalidCursorError | PublicProductNotFoundError,
) -> NoReturn:
    if isinstance(exc, InvalidCursorError):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid cursor",
        ) from exc

    raise HTTPException(
        status_code=http_status.HTTP_404_NOT_FOUND,
        detail="Product not found",
    ) from exc


@router.get("", response_model=CursorPage[PublicProductRead])
async def list_public_products(
    language: LocaleFromPath,
    pool: DbPool,
    category_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> CursorPage[PublicProductRead]:
    try:
        return await list_public_products_service(
            pool=pool,
            language=language,
            category_id=category_id,
            limit=limit,
            cursor=cursor,
        )
    except InvalidCursorError as exc:
        _raise_product_http_error(exc)


@router.get("/{product_id}", response_model=PublicProductRead)
async def read_public_product(
    language: LocaleFromPath,
    product_id: UUID,
    pool: DbPool,
) -> PublicProductRead:
    try:
        return await get_public_product(pool, language, product_id)
    except PublicProductNotFoundError as exc:
        _raise_product_http_error(exc)
