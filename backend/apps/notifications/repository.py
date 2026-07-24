import hashlib
from collections.abc import Mapping
from typing import Literal, cast
from uuid import UUID

import asyncpg

from backend.apps.notifications.schemas import FcmPlatform

FcmRegistrationType = Literal["fid", "token"]


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
