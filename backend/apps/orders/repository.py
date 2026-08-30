from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import asyncpg

from backend.apps.common.db import json_object
from backend.apps.common.enums import OrderStatus, PaymentMethod, PaymentStatus
from backend.apps.common.pagination import page_count, page_offset
from backend.apps.orders.exceptions import OrderNotFoundError
from backend.apps.orders.schemas import (
    DeliveryAddressSnapshot,
    OrderItemRead,
    OrderListResponse,
    OrderRead,
    OrderSummaryRead,
)
from backend.apps.products.schemas import LocalizedText
from backend.apps.users.addresses.enums import ArmeniaRegion, Country

ORDER_COLUMNS = """
    o.id,
    o.order_number,
    o.user_id,
    o.status,
    o.payment_method,
    o.payment_status,
    o.subtotal,
    o.delivery_fee,
    o.total,
    o.currency,
    o.customer_first_name,
    o.customer_last_name,
    o.customer_email,
    o.contact_phone,
    o.delivery_address_id,
    o.delivery_country,
    o.delivery_region,
    o.delivery_city,
    o.delivery_street,
    o.delivery_building_number,
    o.delivery_entrance,
    o.delivery_floor,
    o.requested_delivery_at,
    o.delivery_notes,
    o.request_fingerprint,
    o.created_at,
    o.updated_at
"""

ORDER_ITEM_COLUMNS = """
    oi.id,
    oi.product_id,
    oi.product_slug,
    oi.product_title,
    oi.unit_price,
    oi.quantity,
    oi.line_total
"""


def order_item_from_record(record: Mapping[str, object]) -> OrderItemRead:
    return OrderItemRead(
        id=cast(UUID, record["id"]),
        product_id=cast(UUID | None, record["product_id"]),
        product_slug=cast(str | None, record["product_slug"]),
        product_title=LocalizedText.model_validate(json_object(record["product_title"])),
        unit_price=cast(Decimal, record["unit_price"]),
        quantity=cast(int, record["quantity"]),
        line_total=cast(Decimal, record["line_total"]),
    )


def order_summary_from_record(record: Mapping[str, object]) -> OrderSummaryRead:
    return OrderSummaryRead(
        id=cast(UUID, record["id"]),
        order_number=cast(str, record["order_number"]),
        user_id=cast(UUID, record["user_id"]),
        status=OrderStatus(cast(str, record["status"])),
        payment_method=PaymentMethod(cast(str, record["payment_method"])),
        payment_status=PaymentStatus(cast(str, record["payment_status"])),
        subtotal=cast(Decimal, record["subtotal"]),
        delivery_fee=cast(Decimal, record["delivery_fee"]),
        total=cast(Decimal, record["total"]),
        currency=cast(str, record["currency"]),
        customer_first_name=cast(str | None, record["customer_first_name"]),
        customer_last_name=cast(str | None, record["customer_last_name"]),
        customer_email=cast(str, record["customer_email"]),
        contact_phone=cast(str, record["contact_phone"]),
        requested_delivery_at=cast(datetime | None, record["requested_delivery_at"]),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


def order_from_records(
    order_record: Mapping[str, object],
    item_records: Sequence[Mapping[str, object]],
) -> OrderRead:
    summary = order_summary_from_record(order_record)
    return OrderRead(
        **summary.model_dump(),
        delivery_address=DeliveryAddressSnapshot(
            country=Country(cast(str, order_record["delivery_country"])),
            region=ArmeniaRegion(cast(str, order_record["delivery_region"])),
            city=cast(str, order_record["delivery_city"]),
            street=cast(str, order_record["delivery_street"]),
            building_number=cast(str, order_record["delivery_building_number"]),
            entrance=cast(str | None, order_record["delivery_entrance"]),
            floor=cast(str | None, order_record["delivery_floor"]),
        ),
        delivery_notes=cast(str | None, order_record["delivery_notes"]),
        items=[order_item_from_record(record) for record in item_records],
    )


async def list_orders(
    pool: asyncpg.Pool,
    *,
    user_id: UUID | None,
    status: OrderStatus | None,
    payment_method: PaymentMethod | None,
    page: int,
    limit: int,
) -> OrderListResponse:
    conditions: list[str] = []
    params: list[Any] = []

    if user_id is not None:
        params.append(user_id)
        conditions.append(f"o.user_id = ${len(params)}")
    if status is not None:
        params.append(status.value)
        conditions.append(f"o.status = ${len(params)}")
    if payment_method is not None:
        params.append(payment_method.value)
        conditions.append(f"o.payment_method = ${len(params)}")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    count_row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(f"SELECT count(*) AS total FROM orders AS o {where_clause}", *params),
    )
    total = cast(int, count_row["total"]) if count_row is not None else 0

    params.extend([limit, page_offset(page, limit)])
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {ORDER_COLUMNS}
            FROM orders AS o
            {where_clause}
            ORDER BY o.created_at DESC, o.id DESC
            LIMIT ${len(params) - 1}
            OFFSET ${len(params)}
            """,
            *params,
        ),
    )
    return OrderListResponse(
        items=[order_summary_from_record(row) for row in rows],
        total=total,
        page=page,
        limit=limit,
        total_pages=page_count(total, limit),
    )


async def _get_order(
    pool: asyncpg.Pool,
    order_id: UUID,
    user_id: UUID | None,
) -> OrderRead:
    params: list[object] = [order_id]
    user_condition = ""
    if user_id is not None:
        params.append(user_id)
        user_condition = "AND o.user_id = $2"

    order_row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {ORDER_COLUMNS}
            FROM orders AS o
            WHERE o.id = $1 {user_condition}
            """,
            *params,
        ),
    )
    if order_row is None:
        raise OrderNotFoundError

    item_rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {ORDER_ITEM_COLUMNS}
            FROM order_items AS oi
            WHERE oi.order_id = $1
            ORDER BY oi.position
            """,
            order_id,
        ),
    )
    return order_from_records(order_row, item_rows)


async def get_user_order(pool: asyncpg.Pool, user_id: UUID, order_id: UUID) -> OrderRead:
    return await _get_order(pool, order_id, user_id)


async def get_admin_order(pool: asyncpg.Pool, order_id: UUID) -> OrderRead:
    return await _get_order(pool, order_id, None)
