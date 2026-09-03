import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import cast
from uuid import UUID

import asyncpg

from backend.apps.checkout.exceptions import (
    CheckoutAddressNotFoundError,
    EmptyCartError,
    IdempotencyConflictError,
)
from backend.apps.common.db import json_object
from backend.apps.orders.repository import (
    ORDER_COLUMNS,
    ORDER_ITEM_COLUMNS,
    order_from_records,
)
from backend.apps.orders.schemas import OrderRead, PlaceOrderRequest


async def _fetch_order_items(
    connection: asyncpg.Connection,
    order_id: UUID,
) -> Sequence[Mapping[str, object]]:
    return cast(
        Sequence[Mapping[str, object]],
        await connection.fetch(
            f"""
            SELECT {ORDER_ITEM_COLUMNS}
            FROM order_items AS oi
            WHERE oi.order_id = $1
            ORDER BY oi.position
            """,
            order_id,
        ),
    )


async def place_order(
    pool: asyncpg.Pool,
    user_id: UUID,
    payload: PlaceOrderRequest,
    idempotency_key: str,
    request_fingerprint: str,
    currency: str,
) -> OrderRead:
    async with pool.acquire() as connection, connection.transaction():
        # Serialize checkout attempts for one user so two different requests cannot consume
        # the same cart, and so an idempotent retry observes the committed first order.
        await connection.fetchval(
            "SELECT pg_advisory_xact_lock(hashtextextended($1::text, 0))",
            str(user_id),
        )

        existing_order = cast(
            Mapping[str, object] | None,
            await connection.fetchrow(
                f"""
                SELECT {ORDER_COLUMNS}
                FROM orders AS o
                WHERE o.user_id = $1 AND o.idempotency_key = $2
                """,
                user_id,
                idempotency_key,
            ),
        )
        if existing_order is not None:
            if existing_order["request_fingerprint"] != request_fingerprint:
                raise IdempotencyConflictError
            order_id = cast(UUID, existing_order["id"])
            return order_from_records(
                existing_order,
                await _fetch_order_items(connection, order_id),
            )

        address = cast(
            Mapping[str, object] | None,
            await connection.fetchrow(
                """
                SELECT
                    a.id,
                    a.country,
                    a.region::text AS region,
                    a.city,
                    a.street,
                    a.building_number,
                    a.entrance,
                    a.floor,
                    a.apartment,
                    a.latitude,
                    a.longitude,
                    a.formatted_address,
                    a.location_source,
                    u.first_name,
                    u.last_name,
                    u.email
                FROM user_addresses AS a
                INNER JOIN users AS u ON u.id = a.user_id
                WHERE a.id = $1 AND a.user_id = $2
                FOR SHARE OF a, u
                """,
                payload.address_id,
                user_id,
            ),
        )
        if address is None:
            raise CheckoutAddressNotFoundError

        cart_items = cast(
            Sequence[Mapping[str, object]],
            await connection.fetch(
                """
                SELECT
                    ci.product_id,
                    ci.quantity,
                    p.slug,
                    p.title,
                    p.price
                FROM user_cart_items AS ci
                INNER JOIN products AS p ON p.id = ci.product_id
                WHERE ci.user_id = $1
                ORDER BY ci.created_at, ci.product_id
                FOR UPDATE OF ci
                FOR SHARE OF p
                """,
                user_id,
            ),
        )
        if not cart_items:
            raise EmptyCartError

        subtotal = sum(
            (cast(Decimal, item["price"]) * cast(int, item["quantity"]) for item in cart_items),
            start=Decimal(),
        )
        order_row = cast(
            Mapping[str, object] | None,
            await connection.fetchrow(
                f"""
                INSERT INTO orders (
                    user_id,
                    payment_method,
                    subtotal,
                    currency,
                    customer_first_name,
                    customer_last_name,
                    customer_email,
                    contact_phone,
                    delivery_address_id,
                    delivery_country,
                    delivery_region,
                    delivery_city,
                    delivery_street,
                    delivery_building_number,
                    delivery_entrance,
                    delivery_floor,
                    delivery_apartment,
                    delivery_latitude,
                    delivery_longitude,
                    delivery_formatted_address,
                    delivery_location_source,
                    requested_delivery_at,
                    delivery_notes,
                    idempotency_key,
                    request_fingerprint
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                    $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25
                )
                RETURNING {ORDER_COLUMNS.replace("o.", "")}
                """,
                user_id,
                payload.payment_method.value,
                subtotal,
                currency,
                address["first_name"],
                address["last_name"],
                address["email"],
                payload.contact_phone,
                address["id"],
                address["country"],
                address["region"],
                address["city"],
                address["street"],
                address["building_number"],
                address["entrance"],
                address["floor"],
                address["apartment"],
                address["latitude"],
                address["longitude"],
                address["formatted_address"],
                address["location_source"],
                payload.requested_delivery_at,
                payload.delivery_notes,
                idempotency_key,
                request_fingerprint,
            ),
        )
        if order_row is None:
            raise RuntimeError("Order insert did not return a row")

        product_ids = [cast(UUID, item["product_id"]) for item in cart_items]
        product_slugs = [cast(str | None, item["slug"]) for item in cart_items]
        product_titles = [
            json.dumps(json_object(item["title"]), separators=(",", ":")) for item in cart_items
        ]
        unit_prices = [cast(Decimal, item["price"]) for item in cart_items]
        quantities = [cast(int, item["quantity"]) for item in cart_items]
        order_id = cast(UUID, order_row["id"])
        item_rows = cast(
            Sequence[Mapping[str, object]],
            await connection.fetch(
                f"""
                INSERT INTO order_items (
                    order_id,
                    product_id,
                    product_slug,
                    product_title,
                    unit_price,
                    quantity,
                    position
                )
                SELECT
                    $1,
                    item.product_id,
                    item.product_slug,
                    item.product_title,
                    item.unit_price,
                    item.quantity,
                    item.position
                FROM unnest(
                    $2::uuid[],
                    $3::text[],
                    $4::jsonb[],
                    $5::numeric[],
                    $6::integer[]
                ) WITH ORDINALITY AS item(
                    product_id,
                    product_slug,
                    product_title,
                    unit_price,
                    quantity,
                    position
                )
                RETURNING {ORDER_ITEM_COLUMNS.replace("oi.", "")}
                """,
                order_id,
                product_ids,
                product_slugs,
                product_titles,
                unit_prices,
                quantities,
            ),
        )
        if len(item_rows) != len(cart_items):
            raise RuntimeError("Order item insert count did not match the cart")

        await connection.execute(
            """
            DELETE FROM user_cart_items
            WHERE user_id = $1 AND product_id = ANY($2::uuid[])
            """,
            user_id,
            product_ids,
        )
        return order_from_records(order_row, item_rows)
