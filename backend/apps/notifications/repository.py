import hashlib
from collections.abc import Mapping
from typing import Any, Literal, cast
from uuid import UUID

import asyncpg

from backend.apps.notifications.schemas import (
    FcmPlatform,
    NotificationPreferencesRead,
    NotificationPreferencesUpdate,
)

FcmRegistrationType = Literal["fid", "token"]

NOTIFICATION_PREFERENCE_COLUMNS = """
    order_confirmations,
    delivery_updates,
    subscription_reminders,
    weekly_newsletter,
    promotional_offers,
    new_menu_items
"""

NOTIFICATION_PREFERENCE_FIELDS = (
    "order_confirmations",
    "delivery_updates",
    "subscription_reminders",
    "weekly_newsletter",
    "promotional_offers",
    "new_menu_items",
)


def notification_preferences_from_record(
    record: Mapping[str, object],
) -> NotificationPreferencesRead:
    return NotificationPreferencesRead(
        order_confirmations=cast(bool, record["order_confirmations"]),
        delivery_updates=cast(bool, record["delivery_updates"]),
        subscription_reminders=cast(bool, record["subscription_reminders"]),
        weekly_newsletter=cast(bool, record["weekly_newsletter"]),
        promotional_offers=cast(bool, record["promotional_offers"]),
        new_menu_items=cast(bool, record["new_menu_items"]),
    )


def _registration_hash(
    registration_id: str,
    registration_type: FcmRegistrationType,
) -> bytes:
    hash_input = f"{registration_type}\0{registration_id}".encode()
    return hashlib.sha256(hash_input).digest()


async def upsert_registration(
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


async def remove_registration(
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


async def get_latest_registration(
    pool: asyncpg.Pool,
    user_id: UUID,
) -> tuple[str, FcmRegistrationType] | None:
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
        return None
    return (
        cast(str, registration["registration_id"]),
        cast(FcmRegistrationType, registration["registration_type"]),
    )


async def get_notification_preferences(
    pool: asyncpg.Pool,
    user_id: UUID,
) -> NotificationPreferencesRead:
    record = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {NOTIFICATION_PREFERENCE_COLUMNS}
            FROM user_notification_preferences
            WHERE user_id = $1
            """,
            user_id,
        ),
    )
    if record is None:
        raise RuntimeError("Notification preferences are missing for the current user")
    return notification_preferences_from_record(record)


async def update_notification_preferences(
    pool: asyncpg.Pool,
    user_id: UUID,
    payload: NotificationPreferencesUpdate,
) -> NotificationPreferencesRead:
    fields = [
        field_name
        for field_name in NOTIFICATION_PREFERENCE_FIELDS
        if field_name in payload.model_fields_set
    ]
    params: list[Any] = [user_id]
    params.extend(cast(bool, getattr(payload, field_name)) for field_name in fields)

    columns = ["user_id", *fields]
    placeholders = [f"${index}" for index in range(1, len(params) + 1)]
    assignments = [f"{field_name} = EXCLUDED.{field_name}" for field_name in fields]

    record = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            INSERT INTO user_notification_preferences ({", ".join(columns)})
            VALUES ({", ".join(placeholders)})
            ON CONFLICT (user_id) DO UPDATE
            SET {", ".join(assignments)}
            RETURNING {NOTIFICATION_PREFERENCE_COLUMNS}
            """,
            *params,
        ),
    )
    if record is None:
        raise RuntimeError("Notification preferences update did not return a row")
    return notification_preferences_from_record(record)
