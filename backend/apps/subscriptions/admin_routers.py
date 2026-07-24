from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response
from fastapi import status as http_status

from backend.apps.common.enums import SubscriptionPlanStatus
from backend.apps.subscriptions.admin_service import (
    create_subscription_plan,
    delete_subscription_plan,
    get_subscription_plan,
    list_subscription_plans,
    update_subscription_plan,
)
from backend.apps.subscriptions.schemas import (
    SubscriptionPlanCreate,
    SubscriptionPlanListResponse,
    SubscriptionPlanRead,
    SubscriptionPlanUpdate,
)
from backend.config.database import DbPool

router = APIRouter(prefix="/subscriptions", tags=["admin:subscriptions"])


@router.post(
    "",
    response_model=SubscriptionPlanRead,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_admin_subscription_plan(
    payload: SubscriptionPlanCreate,
    pool: DbPool,
) -> SubscriptionPlanRead:
    return await create_subscription_plan(pool, payload)


@router.get("", response_model=SubscriptionPlanListResponse)
async def list_admin_subscription_plans(
    pool: DbPool,
    status_filter: Annotated[SubscriptionPlanStatus | None, Query(alias="status")] = None,
    is_popular: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> SubscriptionPlanListResponse:
    return await list_subscription_plans(
        pool=pool,
        status_filter=status_filter,
        is_popular=is_popular,
        page=page,
        limit=limit,
    )


@router.get("/{subscription_plan_id}", response_model=SubscriptionPlanRead)
async def read_admin_subscription_plan(
    subscription_plan_id: UUID,
    pool: DbPool,
) -> SubscriptionPlanRead:
    return await get_subscription_plan(pool, subscription_plan_id)


@router.patch("/{subscription_plan_id}", response_model=SubscriptionPlanRead)
async def update_admin_subscription_plan(
    subscription_plan_id: UUID,
    payload: SubscriptionPlanUpdate,
    pool: DbPool,
) -> SubscriptionPlanRead:
    return await update_subscription_plan(pool, subscription_plan_id, payload)


@router.delete("/{subscription_plan_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_admin_subscription_plan(
    subscription_plan_id: UUID,
    pool: DbPool,
) -> Response:
    await delete_subscription_plan(pool, subscription_plan_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
