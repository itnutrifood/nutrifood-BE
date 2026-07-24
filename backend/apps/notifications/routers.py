from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status

from backend.apps.accounts.auth import DbPool, RequireAuth
from backend.apps.notifications.schemas import (
    FcmInstallationRegistration,
    FcmInstallationRemoval,
    FcmTokenRegistration,
    FcmTokenRemoval,
    TestNotificationRead,
)
from backend.apps.notifications.security import require_non_production_environment
from backend.apps.notifications.service import (
    FcmRegistrationNotFoundError,
    register_fcm_installation,
    register_fcm_token,
    remove_fcm_installation,
    remove_fcm_token,
    send_test_notification,
)
from backend.config.firebase import FirebaseServiceDependency

router = APIRouter(prefix="/notifications", tags=["notifications"])


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
    try:
        message_id = await send_test_notification(pool, firebase_service, current_user.id)
    except FcmRegistrationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No FCM registration found for the current user",
        ) from exc
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
