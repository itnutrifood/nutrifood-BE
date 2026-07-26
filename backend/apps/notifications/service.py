from uuid import UUID

import asyncpg
from firebase_admin import messaging

from backend.apps.notifications import repository
from backend.apps.notifications.exceptions import FcmRegistrationNotFoundError
from backend.apps.notifications.schemas import (
    FcmInstallationRegistration,
    FcmInstallationRemoval,
    FcmTokenRegistration,
    FcmTokenRemoval,
    NotificationPreferencesRead,
    NotificationPreferencesUpdate,
)
from backend.config.firebase import FirebaseService

TEST_NOTIFICATION_TITLE = "NutriFood test notification"
TEST_NOTIFICATION_BODY = "Firebase Cloud Messaging is configured correctly."


async def register_fcm_installation(
    pool: asyncpg.Pool,
    user_id: UUID,
    payload: FcmInstallationRegistration,
) -> None:
    await repository.upsert_registration(
        pool,
        user_id=user_id,
        registration_id=payload.fid,
        registration_type="fid",
        platform=payload.platform,
    )


async def remove_fcm_installation(
    pool: asyncpg.Pool,
    user_id: UUID,
    payload: FcmInstallationRemoval,
) -> None:
    await repository.remove_registration(
        pool,
        user_id=user_id,
        registration_id=payload.fid,
        registration_type="fid",
    )


async def register_fcm_token(
    pool: asyncpg.Pool,
    user_id: UUID,
    payload: FcmTokenRegistration,
) -> None:
    await repository.upsert_registration(
        pool,
        user_id=user_id,
        registration_id=payload.token,
        registration_type="token",
        platform=payload.platform,
    )


async def remove_fcm_token(
    pool: asyncpg.Pool,
    user_id: UUID,
    payload: FcmTokenRemoval,
) -> None:
    await repository.remove_registration(
        pool,
        user_id=user_id,
        registration_id=payload.token,
        registration_type="token",
    )


async def send_test_notification(
    pool: asyncpg.Pool,
    firebase_service: FirebaseService,
    user_id: UUID,
) -> str:
    registration = await repository.get_latest_registration(pool, user_id)
    if registration is None:
        raise FcmRegistrationNotFoundError

    registration_id, registration_type = registration
    message = messaging.Message(
        fid=registration_id if registration_type == "fid" else None,
        token=registration_id if registration_type == "token" else None,
        notification=messaging.Notification(
            title=TEST_NOTIFICATION_TITLE,
            body=TEST_NOTIFICATION_BODY,
        ),
        data={"type": "test_notification"},
    )
    return await firebase_service.send(message)


async def get_notification_preferences(
    pool: asyncpg.Pool,
    user_id: UUID,
) -> NotificationPreferencesRead:
    return await repository.get_notification_preferences(pool, user_id)


async def update_notification_preferences(
    pool: asyncpg.Pool,
    user_id: UUID,
    payload: NotificationPreferencesUpdate,
) -> NotificationPreferencesRead:
    return await repository.update_notification_preferences(pool, user_id, payload)
