from uuid import UUID

import asyncpg

from backend.apps.common.enums import OrderStatus, PaymentMethod
from backend.apps.orders import repository
from backend.apps.orders.schemas import OrderListResponse, OrderRead


async def list_user_orders(
    pool: asyncpg.Pool,
    user_id: UUID,
    status: OrderStatus | None,
    page: int,
    limit: int,
) -> OrderListResponse:
    return await repository.list_orders(
        pool,
        user_id=user_id,
        status=status,
        payment_method=None,
        page=page,
        limit=limit,
    )


async def get_user_order(pool: asyncpg.Pool, user_id: UUID, order_id: UUID) -> OrderRead:
    return await repository.get_user_order(pool, user_id, order_id)


async def list_admin_orders(
    pool: asyncpg.Pool,
    status: OrderStatus | None,
    payment_method: PaymentMethod | None,
    page: int,
    limit: int,
) -> OrderListResponse:
    return await repository.list_orders(
        pool,
        user_id=None,
        status=status,
        payment_method=payment_method,
        page=page,
        limit=limit,
    )


async def get_admin_order(pool: asyncpg.Pool, order_id: UUID) -> OrderRead:
    return await repository.get_admin_order(pool, order_id)
