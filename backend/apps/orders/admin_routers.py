from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from backend.apps.common.enums import OrderStatus, PaymentMethod
from backend.apps.orders.schemas import OrderListResponse, OrderRead
from backend.apps.orders.service import get_admin_order, list_admin_orders
from backend.config.database import DbPool

router = APIRouter(prefix="/orders", tags=["admin:orders"])


@router.get("", response_model=OrderListResponse)
async def list_all_orders(
    pool: DbPool,
    status: Annotated[OrderStatus | None, Query()] = None,
    payment_method: Annotated[PaymentMethod | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> OrderListResponse:
    return await list_admin_orders(pool, status, payment_method, page, limit)


@router.get("/{order_id}", response_model=OrderRead)
async def read_admin_order(order_id: UUID, pool: DbPool) -> OrderRead:
    return await get_admin_order(pool, order_id)
