from typing import Annotated, NoReturn
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from backend.apps.common.localization import LocaleFromPath
from backend.apps.common.pagination import CursorPage, InvalidCursorError
from backend.apps.subscriptions.schemas import PublicSubscriptionPlanRead
from backend.apps.subscriptions.service import (
    PublicSubscriptionPlanNotFoundError,
    get_public_subscription_plan,
)
from backend.apps.subscriptions.service import (
    list_public_subscription_plans as list_public_subscription_plans_service,
)
from backend.config.database import get_pool

DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


def _raise_subscription_plan_http_error(
    exc: InvalidCursorError | PublicSubscriptionPlanNotFoundError,
) -> NoReturn:
    if isinstance(exc, InvalidCursorError):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid cursor",
        ) from exc

    raise HTTPException(
        status_code=http_status.HTTP_404_NOT_FOUND,
        detail="Subscription plan not found",
    ) from exc


@router.get("", response_model=CursorPage[PublicSubscriptionPlanRead])
async def list_public_subscription_plans(
    language: LocaleFromPath,
    pool: DbPool,
    is_popular: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> CursorPage[PublicSubscriptionPlanRead]:
    try:
        return await list_public_subscription_plans_service(
            pool=pool,
            language=language,
            is_popular=is_popular,
            limit=limit,
            cursor=cursor,
        )
    except InvalidCursorError as exc:
        _raise_subscription_plan_http_error(exc)


@router.get("/{subscription_plan_id}", response_model=PublicSubscriptionPlanRead)
async def read_public_subscription_plan(
    language: LocaleFromPath,
    subscription_plan_id: UUID,
    pool: DbPool,
) -> PublicSubscriptionPlanRead:
    try:
        return await get_public_subscription_plan(pool, language, subscription_plan_id)
    except PublicSubscriptionPlanNotFoundError as exc:
        _raise_subscription_plan_http_error(exc)
