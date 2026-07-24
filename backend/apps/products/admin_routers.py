from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response
from fastapi import status as http_status

from backend.apps.products.admin_service import (
    create_product,
    delete_product,
    get_product,
    list_products,
    update_product,
)
from backend.apps.products.schemas import (
    ProductCreate,
    ProductListResponse,
    ProductRead,
    ProductUpdate,
)
from backend.config.database import DbPool

router = APIRouter(prefix="/products", tags=["admin:products"])


@router.post("", response_model=ProductRead, status_code=http_status.HTTP_201_CREATED)
async def create_admin_product(
    payload: ProductCreate,
    pool: DbPool,
) -> ProductRead:
    return await create_product(pool, payload)


@router.get("", response_model=ProductListResponse)
async def list_admin_products(
    pool: DbPool,
    category_id: UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ProductListResponse:
    return await list_products(
        pool=pool,
        category_id=category_id,
        page=page,
        limit=limit,
    )


@router.get("/{product_id}", response_model=ProductRead)
async def read_admin_product(
    product_id: UUID,
    pool: DbPool,
) -> ProductRead:
    return await get_product(pool, product_id)


@router.patch("/{product_id}", response_model=ProductRead)
async def update_admin_product(
    product_id: UUID,
    payload: ProductUpdate,
    pool: DbPool,
) -> ProductRead:
    return await update_product(pool, product_id, payload)


@router.delete("/{product_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_admin_product(
    product_id: UUID,
    pool: DbPool,
) -> Response:
    await delete_product(pool, product_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
