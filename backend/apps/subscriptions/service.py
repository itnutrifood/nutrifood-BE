from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from uuid import UUID

import asyncpg

from backend.apps.common.enums import LanguageCode
from backend.apps.common.exceptions import InvalidCursorError
from backend.apps.common.localization import (
    localized_items,
    localized_text,
    required_localized_text,
)
from backend.apps.common.pagination import (
    CursorPage,
    decode_cursor,
    encode_cursor,
)
from backend.apps.subscriptions import repository
from backend.apps.subscriptions.exceptions import SubscriptionPlanNotFoundError
from backend.apps.subscriptions.schemas import PublicSubscriptionPlanRead, SubscriptionPlanRead

PublicSubscriptionPlanNotFoundError = SubscriptionPlanNotFoundError


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
    parsed_cursor: SubscriptionPlanCursor | None = None
    if cursor is not None:
        parsed_cursor = _parse_subscription_plan_cursor(cursor)

    subscription_plans = await repository.list_active_subscription_plans(
        pool,
        is_popular,
        limit,
        (
            parsed_cursor.sort_order,
            parsed_cursor.price,
            parsed_cursor.slug,
            parsed_cursor.id,
        )
        if parsed_cursor is not None
        else None,
    )
    next_cursor = (
        _subscription_plan_cursor(subscription_plans[limit - 1])
        if len(subscription_plans) > limit
        else None
    )

    return CursorPage(
        items=[
            _public_subscription_plan(subscription_plan, language)
            for subscription_plan in subscription_plans[:limit]
        ],
        limit=limit,
        next_cursor=next_cursor,
    )


async def get_public_subscription_plan(
    pool: asyncpg.Pool,
    language: LanguageCode,
    subscription_plan_id: UUID,
) -> PublicSubscriptionPlanRead:
    subscription_plan = await repository.get_active_subscription_plan(
        pool,
        subscription_plan_id,
    )
    return _public_subscription_plan(subscription_plan, language)


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
