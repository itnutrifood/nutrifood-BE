from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from backend.apps.common.localization import LocaleFromPath
from backend.apps.common.pagination import CursorPage
from backend.apps.subscriptions.schemas import PublicSubscriptionPlanRead
from backend.apps.subscriptions.service import get_public_subscription_plan
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


@router.get("/{subscription_plan_id}", response_model=PublicSubscriptionPlanRead)
async def read_public_subscription_plan(
    language: LocaleFromPath,
    subscription_plan_id: UUID,
    pool: DbPool,
) -> PublicSubscriptionPlanRead:
    return await get_public_subscription_plan(pool, language, subscription_plan_id)
