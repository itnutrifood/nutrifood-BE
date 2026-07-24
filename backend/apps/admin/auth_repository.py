from collections.abc import Mapping
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
