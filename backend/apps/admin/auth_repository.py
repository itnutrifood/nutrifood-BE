import hashlib
from collections.abc import Mapping
from datetime import datetime
from typing import cast
from uuid import UUID

import asyncpg

from backend.apps.admin.auth_schemas import AdminRecord

ADMIN_COLUMNS = """
    id,
    username,
    password_hash,
    is_active,
    token_version
"""


def _jti_hash(jti: UUID) -> str:
    return hashlib.sha256(str(jti).encode("ascii")).hexdigest()


def admin_from_record(record: Mapping[str, object]) -> AdminRecord:
    return AdminRecord(
        id=cast(UUID, record["id"]),
        username=cast(str, record["username"]),
        password_hash=cast(str, record["password_hash"]),
        is_active=cast(bool, record["is_active"]),
        token_version=cast(int, record["token_version"]),
    )


async def get_admin_by_username(
    pool: asyncpg.Pool,
    username: str,
) -> AdminRecord | None:
    record = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {ADMIN_COLUMNS}
            FROM admins
            WHERE username = $1
            """,
            username,
        ),
    )
    return admin_from_record(record) if record is not None else None


async def get_admin_by_id(pool: asyncpg.Pool, admin_id: UUID) -> AdminRecord | None:
    record = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {ADMIN_COLUMNS}
            FROM admins
            WHERE id = $1
            """,
            admin_id,
        ),
    )
    return admin_from_record(record) if record is not None else None


async def mark_admin_login(pool: asyncpg.Pool, admin_id: UUID) -> None:
    await pool.execute(
        """
        UPDATE admins
        SET last_login_at = now(),
            updated_at = now()
        WHERE id = $1
        """,
        admin_id,
    )


async def mark_admin_refresh(pool: asyncpg.Pool, admin_id: UUID) -> None:
    await pool.execute(
        """
        UPDATE admins
        SET last_refresh_at = now(),
            updated_at = now()
        WHERE id = $1
        """,
        admin_id,
    )


async def create_refresh_session(
    pool: asyncpg.Pool,
    *,
    jti: UUID,
    admin_id: UUID,
    family_id: UUID,
    expires_at: datetime,
) -> None:
    await pool.execute(
        """
        INSERT INTO admin_refresh_sessions (
            jti_hash,
            admin_id,
            family_id,
            expires_at
        )
        VALUES ($1, $2, $3, $4)
        """,
        _jti_hash(jti),
        admin_id,
        family_id,
        expires_at,
    )


async def consume_refresh_session(
    pool: asyncpg.Pool,
    *,
    jti: UUID,
    admin_id: UUID,
    family_id: UUID,
) -> bool:
    row = await pool.fetchrow(
        """
        UPDATE admin_refresh_sessions
        SET consumed_at = now()
        WHERE jti_hash = $1
          AND admin_id = $2
          AND family_id = $3
          AND consumed_at IS NULL
          AND revoked_at IS NULL
          AND expires_at > now()
        RETURNING jti_hash
        """,
        _jti_hash(jti),
        admin_id,
        family_id,
    )
    return row is not None


async def revoke_refresh_family(
    pool: asyncpg.Pool,
    *,
    admin_id: UUID,
    family_id: UUID,
) -> None:
    await pool.execute(
        """
        UPDATE admin_refresh_sessions
        SET revoked_at = now()
        WHERE admin_id = $1
          AND family_id = $2
          AND revoked_at IS NULL
        """,
        admin_id,
        family_id,
    )
