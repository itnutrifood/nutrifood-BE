from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import cast
from uuid import UUID

import asyncpg

from backend.apps.admin.subscriptions import (
    SUBSCRIPTION_PLAN_COLUMNS,
    SubscriptionPlanRead,
    _subscription_plan_from_record,
)
from backend.apps.common.enums import LanguageCode, SubscriptionPlanStatus
from backend.apps.common.localization import (
    localized_items,
    localized_text,
    required_localized_text,
)
from backend.apps.common.pagination import (
    CursorPage,
    InvalidCursorError,
    decode_cursor,
    encode_cursor,
)
from backend.apps.subscriptions.schemas import PublicSubscriptionPlanRead


class PublicSubscriptionPlanNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class SubscriptionPlanCursor:
    sort_order: int
    price: Decimal
    slug: str
    id: UUID


def _parse_subscription_plan_cursor(cursor: str) -> SubscriptionPlanCursor:
    payload = decode_cursor(cursor)

    sort_order = payload.get("sort_order")
    price = payload.get("price")
    slug = payload.get("slug")
    subscription_plan_id = payload.get("id")

    if isinstance(sort_order, bool) or not isinstance(sort_order, int):
        raise InvalidCursorError("Invalid subscription cursor")
    if not isinstance(price, str) or not price:
        raise InvalidCursorError("Invalid subscription cursor")
    if not isinstance(slug, str) or not slug:
        raise InvalidCursorError("Invalid subscription cursor")
    if not isinstance(subscription_plan_id, str):
        raise InvalidCursorError("Invalid subscription cursor")

    try:
        parsed_price = Decimal(price)
        parsed_subscription_plan_id = UUID(subscription_plan_id)
    except (InvalidOperation, ValueError) as exc:
        raise InvalidCursorError("Invalid subscription cursor") from exc

    return SubscriptionPlanCursor(
        sort_order=sort_order,
        price=parsed_price,
        slug=slug,
        id=parsed_subscription_plan_id,
    )


def _subscription_plan_cursor(subscription_plan: SubscriptionPlanRead) -> str:
    return encode_cursor(
        {
            "sort_order": subscription_plan.sort_order,
            "price": subscription_plan.price,
            "slug": subscription_plan.slug,
            "id": subscription_plan.id,
        }
    )


async def list_public_subscription_plans(
    pool: asyncpg.Pool,
    language: LanguageCode,
    is_popular: bool | None,
    limit: int,
    cursor: str | None,
) -> CursorPage[PublicSubscriptionPlanRead]:
    params: list[object] = [SubscriptionPlanStatus.ACTIVE.value]
    conditions = ["status = $1::subscription_plan_status"]

    if is_popular is not None:
        params.append(is_popular)
        conditions.append(f"is_popular = ${len(params)}")

    if cursor is not None:
        subscription_cursor = _parse_subscription_plan_cursor(cursor)
        params.extend(
            [
                subscription_cursor.sort_order,
                subscription_cursor.price,
                subscription_cursor.slug,
                subscription_cursor.id,
            ]
        )
        conditions.append(
            f"""
            (sort_order, price, slug, id) >
            (${len(params) - 3}, ${len(params) - 2}, ${len(params) - 1}, ${len(params)})
            """
        )

    params.append(limit + 1)
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {SUBSCRIPTION_PLAN_COLUMNS}
            FROM subscription_plans
            WHERE {" AND ".join(conditions)}
            ORDER BY sort_order, price, slug, id
            LIMIT ${len(params)}
            """,
            *params,
        ),
    )

    subscription_plans = [_subscription_plan_from_record(row) for row in rows[:limit]]
    next_cursor = _subscription_plan_cursor(subscription_plans[-1]) if len(rows) > limit else None

    return CursorPage(
        items=[
            _public_subscription_plan(subscription_plan, language)
            for subscription_plan in subscription_plans
        ],
        limit=limit,
        next_cursor=next_cursor,
    )


async def get_public_subscription_plan(
    pool: asyncpg.Pool,
    language: LanguageCode,
    subscription_plan_id: UUID,
) -> PublicSubscriptionPlanRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {SUBSCRIPTION_PLAN_COLUMNS}
            FROM subscription_plans
            WHERE id = $1
                AND status = $2::subscription_plan_status
            """,
            subscription_plan_id,
            SubscriptionPlanStatus.ACTIVE.value,
        ),
    )
    if row is None:
        raise PublicSubscriptionPlanNotFoundError

    return _public_subscription_plan(_subscription_plan_from_record(row), language)


def _public_subscription_plan(
    subscription_plan: SubscriptionPlanRead,
    language: LanguageCode,
) -> PublicSubscriptionPlanRead:
    return PublicSubscriptionPlanRead(
        id=subscription_plan.id,
        slug=subscription_plan.slug,
        name=required_localized_text(subscription_plan.name.to_db(), language),
        description=localized_text(subscription_plan.description.to_db(), language),
        price=subscription_plan.price,
        billing_interval=required_localized_text(
            subscription_plan.billing_interval.to_db(), language
        ),
        meal_count_label=localized_text(subscription_plan.meal_count_label.to_db(), language),
        is_popular=subscription_plan.is_popular,
        status=subscription_plan.status,
        sort_order=subscription_plan.sort_order,
        additional_info=localized_items(subscription_plan.additional_info.to_db(), language),
        created_at=subscription_plan.created_at,
        updated_at=subscription_plan.updated_at,
    )
