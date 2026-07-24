import hashlib
from collections.abc import Mapping
from typing import Literal, cast
from uuid import UUID

import asyncpg
from firebase_admin import messaging

from backend.apps.notifications.schemas import (
    FcmInstallationRegistration,
    FcmInstallationRemoval,
    FcmPlatform,
    FcmTokenRegistration,
    FcmTokenRemoval,
)
from backend.config.firebase import FirebaseService

FcmRegistrationType = Literal["fid", "token"]

TEST_NOTIFICATION_TITLE = "NutriFood test notification"
TEST_NOTIFICATION_BODY = "Firebase Cloud Messaging is configured correctly."


class FcmRegistrationNotFoundError(Exception):
    pass


def _registration_hash(
    registration_id: str,
    registration_type: FcmRegistrationType,
) -> bytes:
    hash_input = f"{registration_type}\0{registration_id}".encode()
    return hashlib.sha256(hash_input).digest()


async def _upsert_registration(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    registration_id: str,
    registration_type: FcmRegistrationType,
    platform: FcmPlatform,
) -> None:
    await pool.execute(
        """
        INSERT INTO user_fcm_registrations (
            registration_hash,
            registration_id,
            registration_type,
            user_id,
            platform
        )
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (registration_hash) DO UPDATE
        SET user_id = EXCLUDED.user_id,
            platform = EXCLUDED.platform,
            last_seen_at = now()
        """,
        _registration_hash(registration_id, registration_type),
        registration_id,
        registration_type,
        user_id,
        platform,
    )


async def _remove_registration(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    registration_id: str,
    registration_type: FcmRegistrationType,
) -> None:
    await pool.execute(
        """
        DELETE FROM user_fcm_registrations
        WHERE registration_hash = $1
          AND registration_id = $2
          AND registration_type = $3
          AND user_id = $4
        """,
        _registration_hash(registration_id, registration_type),
        registration_id,
        registration_type,
        user_id,
    )


async def register_fcm_installation(
    pool: asyncpg.Pool,
    user_id: UUID,
    payload: FcmInstallationRegistration,
) -> None:
    await _upsert_registration(
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
    await _remove_registration(
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
    await _upsert_registration(
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
    await _remove_registration(
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
    registration = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            """
            SELECT registration_id, registration_type
            FROM user_fcm_registrations
            WHERE user_id = $1
            ORDER BY
                last_seen_at DESC,
                (registration_type = 'fid') DESC,
                created_at DESC
            LIMIT 1
            """,
            user_id,
        ),
    )
    if registration is None:
        raise FcmRegistrationNotFoundError

    registration_id = cast(str, registration["registration_id"])
    registration_type = cast(FcmRegistrationType, registration["registration_type"])
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
