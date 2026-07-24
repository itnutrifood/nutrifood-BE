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
from backend.apps.admin.security import verify_admin_password
from backend.config.settings import Settings

AdminTokenType = Literal["access", "refresh"]


def ensure_admin_auth_configured(settings: Settings) -> None:
    if not settings.admin_token_secret:
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
        "jti": str(uuid4()),
    }
    return str(
        jwt.encode(payload, settings.admin_token_secret, algorithm=settings.admin_token_algorithm)
    )


def create_admin_token_pair(admin: AdminUser, settings: Settings) -> AdminTokenPair:
    access_delta = _admin_token_delta(settings, "access")
    refresh_delta = _admin_token_delta(settings, "refresh")
    return AdminTokenPair(
        access_token=create_admin_token(admin, "access", settings),
        refresh_token=create_admin_token(admin, "refresh", settings),
        expires_in=_expires_in_seconds(access_delta),
        refresh_expires_in=_expires_in_seconds(refresh_delta),
    )


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
            options={"require": ["admin_id", "exp", "iat", "sub", "token_version", "type"]},
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
    if (
        admin is None
        or not admin.is_active
        or not verify_admin_password(payload.password, admin.password_hash)
    ):
        raise AdminAuthenticationError("Invalid admin credentials")

    await auth_repository.mark_admin_login(pool, admin.id)
    return create_admin_token_pair(admin, settings)


async def refresh_admin_token(
    pool: asyncpg.Pool,
    refresh_token: str,
    settings: Settings,
) -> AdminTokenPair:
    token_payload = decode_admin_token(refresh_token, "refresh", settings)
    admin = await get_admin_from_token_payload(pool, token_payload)
    await auth_repository.mark_admin_refresh(pool, admin.id)
    return create_admin_token_pair(admin, settings)
