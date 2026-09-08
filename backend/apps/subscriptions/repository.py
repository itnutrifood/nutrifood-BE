import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import asyncpg

from backend.apps.common.db import json_object, rows_affected
from backend.apps.common.enums import (
    SubscriptionActivationSource,
    SubscriptionPlanStatus,
    UserSubscriptionStatus,
)
from backend.apps.common.pagination import page_count, page_offset
from backend.apps.subscriptions.exceptions import (
    ActiveSubscriptionConflictError,
    DuplicateSubscriptionPlanSlugError,
    SubscriptionPlanDeleteConflictError,
    SubscriptionPlanNotFoundError,
    UserSubscriptionNotFoundError,
)
from backend.apps.subscriptions.schemas import (
    LocalizedInfoItems,
    LocalizedText,
    OptionalLocalizedText,
    SubscriptionPlanCreate,
    SubscriptionPlanListResponse,
    SubscriptionPlanRead,
    SubscriptionPlanUpdate,
    UserSubscriptionRecord,
)

SUBSCRIPTION_PLAN_COLUMNS = """
    id,
    slug,
    name,
    description,
    price,
    billing_interval,
    meal_count_label,
    is_popular,
    status::text AS status,
    sort_order,
    additional_info,
    created_at,
    updated_at
"""

USER_SUBSCRIPTION_COLUMNS = """
    id,
    user_id,
    subscription_plan_id,
    status::text AS status,
    activation_source::text AS activation_source,
    started_at,
    cancelled_at,
    created_at,
    updated_at
"""


def subscription_plan_from_record(record: Mapping[str, object]) -> SubscriptionPlanRead:
    return SubscriptionPlanRead(
        id=cast(UUID, record["id"]),
        slug=cast(str, record["slug"]),
        name=LocalizedText.model_validate(json_object(record["name"])),
        description=OptionalLocalizedText.model_validate(json_object(record["description"])),
        price=cast(Decimal, record["price"]),
        billing_interval=LocalizedText.model_validate(json_object(record["billing_interval"])),
        meal_count_label=OptionalLocalizedText.model_validate(
            json_object(record["meal_count_label"])
        ),
        is_popular=cast(bool, record["is_popular"]),
        status=SubscriptionPlanStatus(cast(str, record["status"])),
        sort_order=cast(int, record["sort_order"]),
        additional_info=LocalizedInfoItems.model_validate(json_object(record["additional_info"])),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


def user_subscription_from_record(record: Mapping[str, object]) -> UserSubscriptionRecord:
    return UserSubscriptionRecord(
        id=cast(UUID, record["id"]),
        user_id=cast(UUID, record["user_id"]),
        subscription_plan_id=cast(UUID, record["subscription_plan_id"]),
        status=UserSubscriptionStatus(cast(str, record["status"])),
        activation_source=SubscriptionActivationSource(cast(str, record["activation_source"])),
        started_at=cast(datetime, record["started_at"]),
        cancelled_at=cast(datetime | None, record["cancelled_at"]),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


def _optional_localized_text_db_value(value: OptionalLocalizedText | None) -> dict[str, str]:
    return value.to_db() if value is not None else {}


def _localized_info_items_db_value(value: LocalizedInfoItems | None) -> dict[str, list[str]]:
    return value.to_db() if value is not None else {}


async def create_subscription_plan(
    pool: asyncpg.Pool,
    payload: SubscriptionPlanCreate,
) -> SubscriptionPlanRead:
    try:
        row = cast(
            Mapping[str, object] | None,
            await pool.fetchrow(
                f"""
                INSERT INTO subscription_plans (
                    slug,
                    name,
                    description,
                    price,
                    billing_interval,
                    meal_count_label,
                    is_popular,
                    status,
                    sort_order,
                    additional_info
                )
                VALUES (
                    $1,
                    $2::jsonb,
                    $3::jsonb,
                    $4,
                    $5::jsonb,
                    $6::jsonb,
                    $7,
                    $8::subscription_plan_status,
                    $9,
                    $10::jsonb
                )
                RETURNING {SUBSCRIPTION_PLAN_COLUMNS}
                """,
                payload.slug,
                json.dumps(payload.name.to_db()),
                json.dumps(payload.description.to_db()),
                payload.price,
                json.dumps(payload.billing_interval.to_db()),
                json.dumps(payload.meal_count_label.to_db()),
                payload.is_popular,
                payload.status.value,
                payload.sort_order,
                json.dumps(payload.additional_info.to_db()),
            ),
        )
    except asyncpg.UniqueViolationError as exc:
        raise DuplicateSubscriptionPlanSlugError from exc

    if row is None:
        raise RuntimeError("Subscription plan insert did not return a row")

    return subscription_plan_from_record(row)


async def get_subscription_plan(
    pool: asyncpg.Pool,
    subscription_plan_id: UUID,
) -> SubscriptionPlanRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {SUBSCRIPTION_PLAN_COLUMNS}
            FROM subscription_plans
            WHERE id = $1
            """,
            subscription_plan_id,
        ),
    )
    if row is None:
        raise SubscriptionPlanNotFoundError

    return subscription_plan_from_record(row)


async def list_subscription_plans(
    pool: asyncpg.Pool,
    status_filter: SubscriptionPlanStatus | None,
    is_popular: bool | None,
    page: int,
    limit: int,
) -> SubscriptionPlanListResponse:
    conditions: list[str] = []
    params: list[Any] = []

    if status_filter is not None:
        params.append(status_filter.value)
        conditions.append(f"status = ${len(params)}::subscription_plan_status")

    if is_popular is not None:
        params.append(is_popular)
        conditions.append(f"is_popular = ${len(params)}")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    count_row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"SELECT count(*) AS total FROM subscription_plans {where_clause}",
            *params,
        ),
    )
    total = cast(int, count_row["total"]) if count_row is not None else 0

    params.extend([limit, page_offset(page, limit)])
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {SUBSCRIPTION_PLAN_COLUMNS}
            FROM subscription_plans
            {where_clause}
            ORDER BY sort_order, price, slug
            LIMIT ${len(params) - 1}
            OFFSET ${len(params)}
            """,
            *params,
        ),
    )

    return SubscriptionPlanListResponse(
        items=[subscription_plan_from_record(row) for row in rows],
        total=total,
        page=page,
        limit=limit,
        total_pages=page_count(total, limit),
    )


async def update_subscription_plan(
    pool: asyncpg.Pool,
    subscription_plan_id: UUID,
    payload: SubscriptionPlanUpdate,
) -> SubscriptionPlanRead:
    assignments: list[str] = []
    params: list[Any] = []

    if "slug" in payload.model_fields_set:
        params.append(payload.slug)
        assignments.append(f"slug = ${len(params)}")
    if "name" in payload.model_fields_set:
        params.append(json.dumps(cast(LocalizedText, payload.name).to_db()))
        assignments.append(f"name = ${len(params)}::jsonb")
    if "description" in payload.model_fields_set:
        params.append(json.dumps(_optional_localized_text_db_value(payload.description)))
        assignments.append(f"description = ${len(params)}::jsonb")
    if "price" in payload.model_fields_set:
        params.append(payload.price)
        assignments.append(f"price = ${len(params)}")
    if "billing_interval" in payload.model_fields_set:
        params.append(json.dumps(cast(LocalizedText, payload.billing_interval).to_db()))
        assignments.append(f"billing_interval = ${len(params)}::jsonb")
    if "meal_count_label" in payload.model_fields_set:
        params.append(json.dumps(_optional_localized_text_db_value(payload.meal_count_label)))
        assignments.append(f"meal_count_label = ${len(params)}::jsonb")
    if "is_popular" in payload.model_fields_set:
        params.append(payload.is_popular)
        assignments.append(f"is_popular = ${len(params)}")
    if "status" in payload.model_fields_set:
        params.append(cast(SubscriptionPlanStatus, payload.status).value)
        assignments.append(f"status = ${len(params)}::subscription_plan_status")
    if "sort_order" in payload.model_fields_set:
        params.append(payload.sort_order)
        assignments.append(f"sort_order = ${len(params)}")
    if "additional_info" in payload.model_fields_set:
        params.append(json.dumps(_localized_info_items_db_value(payload.additional_info)))
        assignments.append(f"additional_info = ${len(params)}::jsonb")

    params.append(subscription_plan_id)

    try:
        row = cast(
            Mapping[str, object] | None,
            await pool.fetchrow(
                f"""
                UPDATE subscription_plans
                SET {", ".join(assignments)}
                WHERE id = ${len(params)}
                RETURNING {SUBSCRIPTION_PLAN_COLUMNS}
                """,
                *params,
            ),
        )
    except asyncpg.UniqueViolationError as exc:
        raise DuplicateSubscriptionPlanSlugError from exc

    if row is None:
        raise SubscriptionPlanNotFoundError

    return subscription_plan_from_record(row)


async def delete_subscription_plan(pool: asyncpg.Pool, subscription_plan_id: UUID) -> None:
    try:
        command_status = cast(
            str,
            await pool.execute(
                "DELETE FROM subscription_plans WHERE id = $1",
                subscription_plan_id,
            ),
        )
    except asyncpg.ForeignKeyViolationError as exc:
        raise SubscriptionPlanDeleteConflictError from exc

    if rows_affected(command_status) == 0:
        raise SubscriptionPlanNotFoundError


async def list_active_subscription_plans(
    pool: asyncpg.Pool,
    is_popular: bool | None,
    limit: int,
    cursor: tuple[int, Decimal, str, UUID] | None,
) -> list[SubscriptionPlanRead]:
    params: list[object] = [SubscriptionPlanStatus.ACTIVE.value]
    conditions = ["status = $1::subscription_plan_status"]

    if is_popular is not None:
        params.append(is_popular)
        conditions.append(f"is_popular = ${len(params)}")

    if cursor is not None:
        params.extend(cursor)
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
    return [subscription_plan_from_record(row) for row in rows]


async def get_active_subscription_plan(
    pool: asyncpg.Pool,
    subscription_plan_id: UUID,
) -> SubscriptionPlanRead:
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
        raise SubscriptionPlanNotFoundError

    return subscription_plan_from_record(row)


async def get_active_user_subscription(
    pool: asyncpg.Pool,
    user_id: UUID,
) -> UserSubscriptionRecord:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {USER_SUBSCRIPTION_COLUMNS}
            FROM user_subscriptions
            WHERE user_id = $1
                AND status = $2::user_subscription_status
            """,
            user_id,
            UserSubscriptionStatus.ACTIVE.value,
        ),
    )
    if row is None:
        raise UserSubscriptionNotFoundError

    return user_subscription_from_record(row)


async def create_test_user_subscription(
    pool: asyncpg.Pool,
    user_id: UUID,
    subscription_plan_id: UUID,
) -> tuple[UserSubscriptionRecord, bool]:
    async with pool.acquire() as connection, connection.transaction():
        await connection.fetchval(
            "SELECT id FROM users WHERE id = $1 FOR UPDATE",
            user_id,
        )

        current_row = cast(
            Mapping[str, object] | None,
            await connection.fetchrow(
                f"""
                SELECT {USER_SUBSCRIPTION_COLUMNS}
                FROM user_subscriptions
                WHERE user_id = $1
                    AND status = $2::user_subscription_status
                """,
                user_id,
                UserSubscriptionStatus.ACTIVE.value,
            ),
        )
        if current_row is not None:
            current_subscription = user_subscription_from_record(current_row)
            if current_subscription.subscription_plan_id != subscription_plan_id:
                raise ActiveSubscriptionConflictError(current_subscription.subscription_plan_id)
            return current_subscription, False

        plan_id = await connection.fetchval(
            """
            SELECT id
            FROM subscription_plans
            WHERE id = $1
                AND status = $2::subscription_plan_status
            FOR SHARE
            """,
            subscription_plan_id,
            SubscriptionPlanStatus.ACTIVE.value,
        )
        if plan_id is None:
            raise SubscriptionPlanNotFoundError

        row = cast(
            Mapping[str, object] | None,
            await connection.fetchrow(
                f"""
                INSERT INTO user_subscriptions (
                    user_id,
                    subscription_plan_id,
                    activation_source
                )
                VALUES ($1, $2, $3::subscription_activation_source)
                RETURNING {USER_SUBSCRIPTION_COLUMNS}
                """,
                user_id,
                subscription_plan_id,
                SubscriptionActivationSource.TEST_BYPASS.value,
            ),
        )
        if row is None:
            raise RuntimeError("User subscription insert did not return a row")

        return user_subscription_from_record(row), True


async def cancel_user_subscription(
    pool: asyncpg.Pool,
    user_id: UUID,
    subscription_plan_id: UUID,
) -> None:
    async with pool.acquire() as connection, connection.transaction():
        await connection.fetchval(
            "SELECT id FROM users WHERE id = $1 FOR UPDATE",
            user_id,
        )
        await connection.execute(
            """
            UPDATE user_subscriptions
            SET status = $3::user_subscription_status,
                cancelled_at = now()
            WHERE user_id = $1
                AND subscription_plan_id = $2
                AND status = $4::user_subscription_status
            """,
            user_id,
            subscription_plan_id,
            UserSubscriptionStatus.CANCELLED.value,
            UserSubscriptionStatus.ACTIVE.value,
        )
