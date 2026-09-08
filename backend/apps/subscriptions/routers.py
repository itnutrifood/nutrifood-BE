from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from fastapi import status as http_status

from backend.apps.accounts.dependencies import RequireAuth
from backend.apps.common.localization import LocaleFromPath
from backend.apps.common.pagination import CursorPage
from backend.apps.subscriptions.schemas import PublicSubscriptionPlanRead, UserSubscriptionRead
from backend.apps.subscriptions.security import require_non_production_environment
from backend.apps.subscriptions.service import (
    activate_test_user_subscription,
    cancel_user_subscription,
    get_current_user_subscription,
    get_public_subscription_plan,
)
from backend.apps.subscriptions.service import (
    list_public_subscription_plans as list_public_subscription_plans_service,
)
from backend.config.database import DbPool

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.get("", response_model=CursorPage[PublicSubscriptionPlanRead])
async def list_public_subscription_plans(
    language: LocaleFromPath,
    pool: DbPool,
    is_popular: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> CursorPage[PublicSubscriptionPlanRead]:
    return await list_public_subscription_plans_service(
        pool=pool,
        language=language,
        is_popular=is_popular,
        limit=limit,
        cursor=cursor,
    )


@router.get("/current", response_model=UserSubscriptionRead)
async def read_current_user_subscription(
    language: LocaleFromPath,
    current_user: RequireAuth,
    pool: DbPool,
) -> UserSubscriptionRead:
    return await get_current_user_subscription(pool, current_user.id, language)


@router.get("/{subscription_plan_id}", response_model=PublicSubscriptionPlanRead)
async def read_public_subscription_plan(
    language: LocaleFromPath,
    subscription_plan_id: UUID,
    pool: DbPool,
) -> PublicSubscriptionPlanRead:
    return await get_public_subscription_plan(pool, language, subscription_plan_id)


@router.post(
    "/{subscription_plan_id}/subscribe",
    response_model=UserSubscriptionRead,
    status_code=http_status.HTTP_201_CREATED,
    responses={
        http_status.HTTP_200_OK: {
            "model": UserSubscriptionRead,
            "description": "The user was already subscribed to this plan.",
        }
    },
    dependencies=[Depends(require_non_production_environment)],
    deprecated=True,
    summary="Temporarily subscribe without payment",
    description=(
        "Non-production testing endpoint. This bypasses payment and will be replaced by "
        "payment-gated activation."
    ),
)
async def temporarily_subscribe_current_user(
    language: LocaleFromPath,
    subscription_plan_id: UUID,
    current_user: RequireAuth,
    pool: DbPool,
    response: Response,
) -> UserSubscriptionRead:
    subscription, created = await activate_test_user_subscription(
        pool,
        current_user.id,
        subscription_plan_id,
        language,
    )
    response.status_code = http_status.HTTP_201_CREATED if created else http_status.HTTP_200_OK
    return subscription


@router.delete(
    "/{subscription_plan_id}/unsubscribe",
    status_code=http_status.HTTP_204_NO_CONTENT,
)
async def unsubscribe_current_user(
    _language: LocaleFromPath,
    subscription_plan_id: UUID,
    current_user: RequireAuth,
    pool: DbPool,
) -> Response:
    await cancel_user_subscription(pool, current_user.id, subscription_plan_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
