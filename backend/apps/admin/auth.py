from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, Self, cast
from uuid import UUID, uuid4

import asyncpg
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.apps.admin.security import verify_admin_password
from backend.config.database import get_pool
from backend.config.settings import Settings, get_settings

AdminTokenType = Literal["access", "refresh"]
DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]

ADMIN_COLUMNS = """
    id,
    username,
    password_hash,
    is_active,
    token_version
"""


class AdminUser(BaseModel):
    id: UUID
    username: str
    token_version: int


class AdminRecord(AdminUser):
    password_hash: str
    is_active: bool


class AdminLoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str | None = Field(default=None, min_length=1)
    email: str | None = Field(default=None, min_length=1)
    password: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identifier(self) -> Self:
        if self.username is None and self.email is None:
            raise ValueError("Username or email is required")
        return self

    @property
    def identifier(self) -> str:
        identifier = self.username or self.email
        if identifier is None:
            raise ValueError("Username or email is required")
        return identifier


class AdminRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class AdminTokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int


bearer_scheme = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/auth", tags=["admin:auth"])


def _admin_auth_error(detail: str = "Admin authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _ensure_admin_auth_configured(settings: Settings) -> None:
    if not settings.admin_token_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin authentication is not configured",
        )


def _expires_in_seconds(delta: timedelta) -> int:
    return int(delta.total_seconds())


def _admin_token_delta(settings: Settings, token_type: AdminTokenType) -> timedelta:
    if token_type == "access":
        return timedelta(minutes=settings.admin_access_token_expire_minutes)

    return timedelta(days=settings.admin_refresh_token_expire_days)


def _create_admin_token(
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


def _create_admin_token_pair(admin: AdminUser, settings: Settings) -> AdminTokenPair:
    access_delta = _admin_token_delta(settings, "access")
    refresh_delta = _admin_token_delta(settings, "refresh")
    return AdminTokenPair(
        access_token=_create_admin_token(admin, "access", settings),
        refresh_token=_create_admin_token(admin, "refresh", settings),
        expires_in=_expires_in_seconds(access_delta),
        refresh_expires_in=_expires_in_seconds(refresh_delta),
    )


def _decode_admin_token(
    token: str,
    token_type: AdminTokenType,
    settings: Settings,
) -> dict[str, Any]:
    _ensure_admin_auth_configured(settings)

    try:
        payload = jwt.decode(
            token,
            settings.admin_token_secret,
            algorithms=[settings.admin_token_algorithm],
            options={"require": ["admin_id", "exp", "iat", "sub", "token_version", "type"]},
        )
    except InvalidTokenError:
        raise _admin_auth_error("Invalid admin token") from None

    if payload.get("type") != token_type:
        raise _admin_auth_error("Invalid admin token")

    return payload


def _admin_from_record(record: asyncpg.Record) -> AdminRecord:
    return AdminRecord(
        id=cast(UUID, record["id"]),
        username=cast(str, record["username"]),
        password_hash=cast(str, record["password_hash"]),
        is_active=cast(bool, record["is_active"]),
        token_version=cast(int, record["token_version"]),
    )


async def _get_admin_by_username(pool: asyncpg.Pool, username: str) -> AdminRecord | None:
    record = await pool.fetchrow(
        f"""
        SELECT {ADMIN_COLUMNS}
        FROM admins
        WHERE username = $1
        """,
        username,
    )
    return _admin_from_record(record) if record is not None else None


async def _get_admin_by_id(pool: asyncpg.Pool, admin_id: UUID) -> AdminRecord | None:
    record = await pool.fetchrow(
        f"""
        SELECT {ADMIN_COLUMNS}
        FROM admins
        WHERE id = $1
        """,
        admin_id,
    )
    return _admin_from_record(record) if record is not None else None


async def _get_admin_from_token_payload(
    pool: asyncpg.Pool,
    payload: dict[str, Any],
) -> AdminRecord:
    try:
        admin_id = UUID(str(payload["admin_id"]))
        token_version = int(payload["token_version"])
        username = str(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise _admin_auth_error("Invalid admin token") from None

    admin = await _get_admin_by_id(pool, admin_id)
    if (
        admin is None
        or not admin.is_active
        or admin.username != username
        or admin.token_version != token_version
    ):
        raise _admin_auth_error("Invalid admin token")

    return admin


async def admin_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    pool: DbPool,
) -> AdminUser:
    if credentials is None:
        raise _admin_auth_error()

    payload = _decode_admin_token(credentials.credentials, "access", settings)
    admin = await _get_admin_from_token_payload(pool, payload)
    return AdminUser(id=admin.id, username=admin.username, token_version=admin.token_version)


RequireAdminAuth = Annotated[AdminUser, Depends(admin_auth)]


@router.post("/sign-in", response_model=AdminTokenPair, include_in_schema=False)
@router.post("/login", response_model=AdminTokenPair)
async def login_admin(
    payload: AdminLoginRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    pool: DbPool,
) -> AdminTokenPair:
    _ensure_admin_auth_configured(settings)

    admin = await _get_admin_by_username(pool, payload.identifier)
    if (
        admin is None
        or not admin.is_active
        or not verify_admin_password(payload.password, admin.password_hash)
    ):
        raise _admin_auth_error("Invalid admin credentials")

    await pool.execute(
        """
        UPDATE admins
        SET last_login_at = now(),
            updated_at = now()
        WHERE id = $1
        """,
        admin.id,
    )
    return _create_admin_token_pair(admin, settings)


@router.post("/refresh", response_model=AdminTokenPair)
async def refresh_admin_token(
    payload: AdminRefreshRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    pool: DbPool,
) -> AdminTokenPair:
    token_payload = _decode_admin_token(payload.refresh_token, "refresh", settings)
    admin = await _get_admin_from_token_payload(pool, token_payload)
    await pool.execute(
        """
        UPDATE admins
        SET last_refresh_at = now(),
            updated_at = now()
        WHERE id = $1
        """,
        admin.id,
    )
    return _create_admin_token_pair(admin, settings)
