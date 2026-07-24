from collections.abc import Mapping
from datetime import datetime
from typing import cast
from uuid import UUID

import asyncpg

from backend.apps.accounts.exceptions import (
    AccountConflictError,
    AccountProvisioningError,
    UserWriteConflictError,
)
from backend.apps.accounts.models import FirebaseIdentity
from backend.apps.accounts.schemas import UserRecord

USER_COLUMNS = """
    id,
    firebase_uid,
    first_name,
    last_name,
    email,
    registration_provider,
    is_active,
    created_at,
    updated_at
"""


def user_from_record(record: Mapping[str, object]) -> UserRecord:
    return UserRecord(
        id=cast(UUID, record["id"]),
        firebase_uid=cast(str | None, record["firebase_uid"]),
        first_name=cast(str | None, record["first_name"]),
        last_name=cast(str | None, record["last_name"]),
        email=cast(str, record["email"]),
        registration_provider=cast(str, record["registration_provider"]),
        is_active=cast(bool, record["is_active"]),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


async def get_user_by_firebase_uid(
    pool: asyncpg.Pool,
    uid: str,
) -> UserRecord | None:
    record = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {USER_COLUMNS}
            FROM users
            WHERE firebase_uid = $1
            """,
            uid,
        ),
    )
    return user_from_record(record) if record is not None else None


async def get_user_by_email(pool: asyncpg.Pool, email: str) -> UserRecord | None:
    record = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {USER_COLUMNS}
            FROM users
            WHERE email = $1
            """,
            email,
        ),
    )
    return user_from_record(record) if record is not None else None


async def link_legacy_user(
    pool: asyncpg.Pool,
    user: UserRecord,
    identity: FirebaseIdentity,
) -> UserRecord:
    try:
        record = cast(
            Mapping[str, object] | None,
            await pool.fetchrow(
                f"""
                UPDATE users
                SET firebase_uid = $2,
                    first_name = COALESCE(first_name, $3),
                    last_name = COALESCE(last_name, $4),
                    last_login_at = now()
                WHERE id = $1 AND firebase_uid IS NULL
                RETURNING {USER_COLUMNS}
                """,
                user.id,
                identity.uid,
                identity.first_name,
                identity.last_name,
            ),
        )
    except asyncpg.UniqueViolationError:
        raise AccountConflictError("Firebase account is already linked") from None

    if record is None:
        raise AccountConflictError("Account linking conflict")
    return user_from_record(record)


async def create_user(
    pool: asyncpg.Pool,
    identity: FirebaseIdentity,
) -> UserRecord:
    try:
        record = cast(
            Mapping[str, object] | None,
            await pool.fetchrow(
                f"""
                INSERT INTO users (
                    firebase_uid,
                    first_name,
                    last_name,
                    email,
                    registration_provider,
                    password_hash,
                    last_login_at
                )
                VALUES ($1, $2, $3, $4, $5, NULL, now())
                RETURNING {USER_COLUMNS}
                """,
                identity.uid,
                identity.first_name,
                identity.last_name,
                identity.email,
                identity.sign_in_provider,
            ),
        )
    except asyncpg.UniqueViolationError:
        raise UserWriteConflictError from None

    if record is None:
        raise AccountProvisioningError("Could not create user")
    return user_from_record(record)


async def sync_user_profile(
    pool: asyncpg.Pool,
    user: UserRecord,
    identity: FirebaseIdentity,
) -> UserRecord:
    try:
        record = cast(
            Mapping[str, object] | None,
            await pool.fetchrow(
                f"""
                UPDATE users
                SET email = $2,
                    first_name = COALESCE(first_name, $3),
                    last_name = COALESCE(last_name, $4)
                WHERE id = $1
                  AND (
                      email IS DISTINCT FROM $2
                      OR (first_name IS NULL AND $3 IS NOT NULL)
                      OR (last_name IS NULL AND $4 IS NOT NULL)
                  )
                RETURNING {USER_COLUMNS}
                """,
                user.id,
                identity.email,
                identity.first_name,
                identity.last_name,
            ),
        )
    except asyncpg.UniqueViolationError:
        raise AccountConflictError("Email is already linked to another Firebase account") from None

    return user_from_record(record) if record is not None else user
