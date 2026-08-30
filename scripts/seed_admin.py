#!/usr/bin/env python3

import asyncio
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.apps.admin.security import hash_admin_password  # noqa: E402
from backend.config.settings import get_settings  # noqa: E402

MIN_ADMIN_PASSWORD_LENGTH = 14
PUBLISHED_ADMIN_USERNAME = "admin@mail.com"
PUBLISHED_ADMIN_PASSWORD = "123456"
PUBLISHED_ADMIN_TOKEN_SECRET = "change-me-to-a-long-random-secret"


def validate_admin_seed_configuration(
    username: str,
    password: str,
    token_secret: str,
) -> None:
    errors: list[str] = []
    if not username or not password:
        errors.append("ADMIN_USERNAME and ADMIN_PASSWORD must be configured")
    if username == PUBLISHED_ADMIN_USERNAME:
        errors.append("ADMIN_USERNAME must not use the published example identity")
    if password == PUBLISHED_ADMIN_PASSWORD or len(password) < MIN_ADMIN_PASSWORD_LENGTH:
        errors.append(
            f"ADMIN_PASSWORD must contain at least {MIN_ADMIN_PASSWORD_LENGTH} characters"
        )
    if token_secret == PUBLISHED_ADMIN_TOKEN_SECRET or len(token_secret.encode("utf-8")) < 32:
        errors.append("ADMIN_TOKEN_SECRET must contain at least 32 bytes of unique key material")
    if errors:
        raise SystemExit("; ".join(errors))


async def seed_admin() -> None:
    load_dotenv()
    get_settings.cache_clear()
    settings = get_settings()

    validate_admin_seed_configuration(
        settings.admin_username,
        settings.admin_password,
        settings.admin_token_secret,
    )

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
    print("Remove ADMIN_PASSWORD from the runtime environment after seeding.")


if __name__ == "__main__":
    asyncio.run(seed_admin())
