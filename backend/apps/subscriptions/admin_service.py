from uuid import UUID

import asyncpg

from backend.apps.common.enums import SubscriptionPlanStatus
from backend.apps.subscriptions import repository
from backend.apps.subscriptions.schemas import (
    SubscriptionPlanCreate,
    SubscriptionPlanListResponse,
    SubscriptionPlanRead,
    SubscriptionPlanUpdate,
)


async def create_subscription_plan(
    pool: asyncpg.Pool,
    payload: SubscriptionPlanCreate,
) -> SubscriptionPlanRead:
    return await repository.create_subscription_plan(pool, payload)


async def get_subscription_plan(
    pool: asyncpg.Pool,
    subscription_plan_id: UUID,
) -> SubscriptionPlanRead:
    return await repository.get_subscription_plan(pool, subscription_plan_id)


async def list_subscription_plans(
    pool: asyncpg.Pool,
    status_filter: SubscriptionPlanStatus | None,
    is_popular: bool | None,
    page: int,
    limit: int,
) -> SubscriptionPlanListResponse:
    return await repository.list_subscription_plans(
        pool,
        status_filter,
        is_popular,
        page,
        limit,
    )


async def update_subscription_plan(
    pool: asyncpg.Pool,
    subscription_plan_id: UUID,
    payload: SubscriptionPlanUpdate,
) -> SubscriptionPlanRead:
    return await repository.update_subscription_plan(pool, subscription_plan_id, payload)


async def delete_subscription_plan(pool: asyncpg.Pool, subscription_plan_id: UUID) -> None:
    await repository.delete_subscription_plan(pool, subscription_plan_id)
