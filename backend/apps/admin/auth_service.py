import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

import asyncpg
import jwt
from jwt.exceptions import InvalidTokenError

from backend.apps.admin import auth_repository
from backend.apps.admin.auth_exceptions import (
    AdminAuthenticationError,
    AdminAuthNotConfiguredError,
)
from backend.apps.admin.auth_schemas import (
    AdminLoginRequest,
    AdminRecord,
    AdminTokenPair,
    AdminUser,
)
from backend.apps.admin.security import hash_admin_password, verify_admin_password
from backend.config.settings import Settings

AdminTokenType = Literal["access", "refresh"]
PUBLISHED_ADMIN_TOKEN_SECRET = "change-me-to-a-long-random-secret"
DUMMY_ADMIN_PASSWORD_HASH = hash_admin_password("invalid-admin-password-for-timing-equalization")


def ensure_admin_auth_configured(settings: Settings) -> None:
    if (
        not settings.admin_token_secret
        or settings.admin_token_secret == PUBLISHED_ADMIN_TOKEN_SECRET
        or len(settings.admin_token_secret.encode("utf-8")) < 32
    ):
        raise AdminAuthNotConfiguredError


def _expires_in_seconds(delta: timedelta) -> int:
    return int(delta.total_seconds())


def _admin_token_delta(settings: Settings, token_type: AdminTokenType) -> timedelta:
    if token_type == "access":
        return timedelta(minutes=settings.admin_access_token_expire_minutes)
    return timedelta(days=settings.admin_refresh_token_expire_days)


def create_admin_token(
    admin: AdminUser,
    token_type: AdminTokenType,
    settings: Settings,
    *,
    jti: UUID | None = None,
    family_id: UUID | None = None,
) -> str:
    now = datetime.now(UTC)
    token_delta = _admin_token_delta(settings, token_type)
    payload: dict[str, Any] = {
        "sub": admin.username,
        "admin_id": str(admin.id),
        "token_version": admin.token_version,
        "type": token_type,
        "iat": now,
        "exp": now + token_delta,
        "jti": str(jti or uuid4()),
        "sid": str(family_id or uuid4()),
    }
    return str(
        jwt.encode(payload, settings.admin_token_secret, algorithm=settings.admin_token_algorithm)
    )


def _create_admin_token_pair_with_metadata(
    admin: AdminUser,
    settings: Settings,
    *,
    family_id: UUID | None = None,
) -> tuple[AdminTokenPair, UUID, UUID]:
    access_delta = _admin_token_delta(settings, "access")
    refresh_delta = _admin_token_delta(settings, "refresh")
    resolved_family_id = family_id or uuid4()
    refresh_jti = uuid4()
    return AdminTokenPair(
        access_token=create_admin_token(
            admin,
            "access",
            settings,
            family_id=resolved_family_id,
        ),
        refresh_token=create_admin_token(
            admin,
            "refresh",
            settings,
            jti=refresh_jti,
            family_id=resolved_family_id,
        ),
        expires_in=_expires_in_seconds(access_delta),
        refresh_expires_in=_expires_in_seconds(refresh_delta),
    ), refresh_jti, resolved_family_id


def create_admin_token_pair(admin: AdminUser, settings: Settings) -> AdminTokenPair:
    return _create_admin_token_pair_with_metadata(admin, settings)[0]


def decode_admin_token(
    token: str,
    token_type: AdminTokenType,
    settings: Settings,
) -> dict[str, Any]:
    ensure_admin_auth_configured(settings)
    try:
        payload = jwt.decode(
            token,
            settings.admin_token_secret,
            algorithms=[settings.admin_token_algorithm],
            options={
                "require": [
                    "admin_id",
                    "exp",
                    "iat",
                    "jti",
                    "sid",
                    "sub",
                    "token_version",
                    "type",
                ]
            },
        )
    except InvalidTokenError:
        raise AdminAuthenticationError("Invalid admin token") from None

    if payload.get("type") != token_type:
        raise AdminAuthenticationError("Invalid admin token")
    return payload


async def get_admin_from_token_payload(
    pool: asyncpg.Pool,
    payload: dict[str, Any],
) -> AdminRecord:
    try:
        admin_id = UUID(str(payload["admin_id"]))
        token_version = int(payload["token_version"])
        username = str(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise AdminAuthenticationError("Invalid admin token") from None

    admin = await auth_repository.get_admin_by_id(pool, admin_id)
    if (
        admin is None
        or not admin.is_active
        or admin.username != username
        or admin.token_version != token_version
    ):
        raise AdminAuthenticationError("Invalid admin token")
    return admin


async def authenticate_admin_access(
    pool: asyncpg.Pool,
    token: str,
    settings: Settings,
) -> AdminUser:
    payload = decode_admin_token(token, "access", settings)
    admin = await get_admin_from_token_payload(pool, payload)
    return AdminUser(id=admin.id, username=admin.username, token_version=admin.token_version)


async def login_admin(
    pool: asyncpg.Pool,
    payload: AdminLoginRequest,
    settings: Settings,
) -> AdminTokenPair:
    ensure_admin_auth_configured(settings)
    admin = await auth_repository.get_admin_by_username(pool, payload.identifier)
    password_valid = await asyncio.to_thread(
        verify_admin_password,
        payload.password,
        admin.password_hash if admin is not None else DUMMY_ADMIN_PASSWORD_HASH,
    )
    if admin is None or not admin.is_active or not password_valid:
        raise AdminAuthenticationError("Invalid admin credentials")

    token_pair, refresh_jti, family_id = _create_admin_token_pair_with_metadata(admin, settings)
    refresh_expiry = datetime.now(UTC) + _admin_token_delta(settings, "refresh")
    await auth_repository.create_refresh_session(
        pool,
        jti=refresh_jti,
        admin_id=admin.id,
        family_id=family_id,
        expires_at=refresh_expiry,
    )
    await auth_repository.mark_admin_login(pool, admin.id)
    return token_pair


async def refresh_admin_token(
    pool: asyncpg.Pool,
    refresh_token: str,
    settings: Settings,
) -> AdminTokenPair:
    token_payload = decode_admin_token(refresh_token, "refresh", settings)
    admin = await get_admin_from_token_payload(pool, token_payload)
    try:
        refresh_jti = UUID(str(token_payload["jti"]))
        family_id = UUID(str(token_payload["sid"]))
    except (KeyError, TypeError, ValueError):
        raise AdminAuthenticationError("Invalid admin token") from None

    consumed = await auth_repository.consume_refresh_session(
        pool,
        jti=refresh_jti,
        admin_id=admin.id,
        family_id=family_id,
    )
    if not consumed:
        await auth_repository.revoke_refresh_family(pool, admin_id=admin.id, family_id=family_id)
        raise AdminAuthenticationError("Refresh token has been consumed or revoked")

    token_pair, new_refresh_jti, new_family_id = _create_admin_token_pair_with_metadata(
        admin,
        settings,
        family_id=family_id,
    )
    await auth_repository.create_refresh_session(
        pool,
        jti=new_refresh_jti,
        admin_id=admin.id,
        family_id=new_family_id,
        expires_at=datetime.now(UTC) + _admin_token_delta(settings, "refresh"),
    )
    await auth_repository.mark_admin_refresh(pool, admin.id)
    return token_pair


async def logout_admin(
    pool: asyncpg.Pool,
    refresh_token: str,
    settings: Settings,
) -> None:
    token_payload = decode_admin_token(refresh_token, "refresh", settings)
    admin = await get_admin_from_token_payload(pool, token_payload)
    try:
        family_id = UUID(str(token_payload["sid"]))
    except (KeyError, TypeError, ValueError):
        raise AdminAuthenticationError("Invalid admin token") from None
    await auth_repository.revoke_refresh_family(pool, admin_id=admin.id, family_id=family_id)
