#!/usr/bin/env python3

import asyncio
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.apps.admin.security import hash_admin_password  # noqa: E402
from backend.config.settings import get_settings  # noqa: E402


async def seed_admin() -> None:
    load_dotenv()
    get_settings.cache_clear()
    settings = get_settings()

    if not settings.admin_username or not settings.admin_password:
        raise SystemExit("ADMIN_USERNAME and ADMIN_PASSWORD must be configured")

    password_hash = hash_admin_password(settings.admin_password)
    pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=1)

    try:
        await pool.execute(
            """
            INSERT INTO admins (
                username,
                password_hash,
                is_active,
                token_version
            )
            VALUES ($1, $2, TRUE, 1)
            ON CONFLICT (username) DO UPDATE
            SET password_hash = EXCLUDED.password_hash,
                is_active = TRUE,
                token_version = admins.token_version + 1,
                updated_at = now()
            """,
            settings.admin_username,
            password_hash,
        )
    finally:
        await pool.close()

    print(f"Seeded admin: {settings.admin_username}")


if __name__ == "__main__":
    asyncio.run(seed_admin())
