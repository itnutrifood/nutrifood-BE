"""Compatibility exports for order administration."""

from backend.apps.orders.admin_routers import router
from backend.apps.orders.exceptions import OrderNotFoundError
from backend.apps.orders.schemas import (
    OrderListResponse,
    OrderRead,
    OrderStatusUpdate,
    OrderSummaryRead,
)
from backend.apps.orders.service import (
    get_admin_order,
    list_admin_orders,
    update_admin_order_status,
)
from backend.config.database import DbPool

__all__ = [
    "DbPool",
    "OrderListResponse",
    "OrderNotFoundError",
    "OrderRead",
    "OrderStatusUpdate",
    "OrderSummaryRead",
    "get_admin_order",
    "list_admin_orders",
    "router",
    "update_admin_order_status",
]
