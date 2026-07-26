from typing import Annotated

from fastapi import APIRouter, Body, Depends, status

from backend.apps.accounts.dependencies import RequireAuth
from backend.apps.notifications.schemas import (
    FcmInstallationRegistration,
    FcmInstallationRemoval,
    FcmTokenRegistration,
    FcmTokenRemoval,
    NotificationPreferencesRead,
    NotificationPreferencesUpdate,
    TestNotificationRead,
)
from backend.apps.notifications.security import require_non_production_environment
from backend.apps.notifications.service import (
    get_notification_preferences,
    register_fcm_installation,
    register_fcm_token,
    remove_fcm_installation,
    remove_fcm_token,
    send_test_notification,
    update_notification_preferences,
)
from backend.config.database import DbPool
from backend.config.firebase import FirebaseServiceDependency

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/preferences", response_model=NotificationPreferencesRead)
async def read_current_user_notification_preferences(
    current_user: RequireAuth,
    pool: DbPool,
) -> NotificationPreferencesRead:
    return await get_notification_preferences(pool, current_user.id)


@router.patch("/preferences", response_model=NotificationPreferencesRead)
async def update_current_user_notification_preferences(
    payload: NotificationPreferencesUpdate,
    current_user: RequireAuth,
    pool: DbPool,
) -> NotificationPreferencesRead:
    return await update_notification_preferences(pool, current_user.id, payload)


@router.post(
    "/test",
    response_model=TestNotificationRead,
    dependencies=[Depends(require_non_production_environment)],
)
async def send_test_notification_to_current_user(
    current_user: RequireAuth,
    pool: DbPool,
    firebase_service: FirebaseServiceDependency,
) -> TestNotificationRead:
    message_id = await send_test_notification(pool, firebase_service, current_user.id)
    return TestNotificationRead(message_id=message_id)


@router.put("/fcm-registrations", status_code=status.HTTP_204_NO_CONTENT)
async def register_firebase_installation(
    payload: FcmInstallationRegistration,
    current_user: RequireAuth,
    pool: DbPool,
) -> None:
    await register_fcm_installation(pool, current_user.id, payload)


@router.delete("/fcm-registrations", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_firebase_installation(
    payload: Annotated[FcmInstallationRemoval, Body()],
    current_user: RequireAuth,
    pool: DbPool,
) -> None:
    await remove_fcm_installation(pool, current_user.id, payload)


@router.put(
    "/fcm-tokens",
    status_code=status.HTTP_204_NO_CONTENT,
    deprecated=True,
)
async def register_legacy_fcm_token(
    payload: FcmTokenRegistration,
    current_user: RequireAuth,
    pool: DbPool,
) -> None:
    await register_fcm_token(pool, current_user.id, payload)


@router.delete(
    "/fcm-tokens",
    status_code=status.HTTP_204_NO_CONTENT,
    deprecated=True,
)
async def unregister_legacy_fcm_token(
    payload: Annotated[FcmTokenRemoval, Body()],
    current_user: RequireAuth,
    pool: DbPool,
) -> None:
    await remove_fcm_token(pool, current_user.id, payload)
