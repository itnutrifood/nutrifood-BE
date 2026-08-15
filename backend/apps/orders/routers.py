from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from backend.apps.accounts.dependencies import RequireAuth
from backend.apps.common.enums import OrderStatus
from backend.apps.orders.schemas import OrderListResponse, OrderRead
from backend.apps.orders.service import get_user_order, list_user_orders
from backend.config.database import DbPool

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=OrderListResponse)
async def list_current_user_orders(
    current_user: RequireAuth,
    pool: DbPool,
    status: Annotated[OrderStatus | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> OrderListResponse:
    return await list_user_orders(pool, current_user.id, status, page, limit)


@router.get("/{order_id}", response_model=OrderRead)
async def read_current_user_order(
    order_id: UUID,
    current_user: RequireAuth,
    pool: DbPool,
) -> OrderRead:
    return await get_user_order(pool, current_user.id, order_id)
