from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, Self, cast
from uuid import UUID, uuid4

import asyncpg
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from backend.apps.common.security import hash_password, verify_password
from backend.config.database import get_pool
from backend.config.settings import Settings, get_settings

UserTokenType = Literal["access", "refresh"]
DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

USER_COLUMNS = """
    id,
    first_name,
    last_name,
    email,
    password_hash,
    is_active,
    token_version,
    created_at,
    updated_at
"""


class UserRead(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: EmailStr
    created_at: datetime
    updated_at: datetime


class UserIdentity(UserRead):
    token_version: int


class UserRecord(UserIdentity):
    password_hash: str
    is_active: bool


class UserSignupRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: str = Field(min_length=1, max_length=150)
    last_name: str = Field(min_length=1, max_length=150)
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    confirm_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @model_validator(mode="after")
    def validate_passwords_match(self) -> Self:
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class UserLoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class UserRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class UserTokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int


class UserAuthResponse(UserTokenPair):
    user: UserRead


bearer_scheme = HTTPBearer(auto_error=False)
router = APIRouter(tags=["accounts:auth"])


def _auth_error(detail: str = "Authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _invalid_token_error(token_type: UserTokenType) -> HTTPException:
    return _auth_error(f"Invalid {token_type} token")


def _ensure_user_auth_configured(settings: Settings) -> None:
    if not settings.user_token_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User authentication is not configured",
        )


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _expires_in_seconds(delta: timedelta) -> int:
    return int(delta.total_seconds())


def _user_token_delta(settings: Settings, token_type: UserTokenType) -> timedelta:
    if token_type == "access":
        return timedelta(minutes=settings.user_access_token_expire_minutes)

    return timedelta(days=settings.user_refresh_token_expire_days)


def _read_user(user: UserIdentity) -> UserRead:
    return UserRead(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _create_user_token(
    user: UserIdentity,
    token_type: UserTokenType,
    settings: Settings,
) -> str:
    now = datetime.now(UTC)
    token_delta = _user_token_delta(settings, token_type)
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "email": str(user.email),
        "token_version": user.token_version,
        "type": token_type,
        "iat": now,
        "exp": now + token_delta,
        "jti": str(uuid4()),
    }
    return str(
        jwt.encode(payload, settings.user_token_secret, algorithm=settings.user_token_algorithm)
    )


def _create_user_token_pair(user: UserIdentity, settings: Settings) -> UserTokenPair:
    access_delta = _user_token_delta(settings, "access")
    refresh_delta = _user_token_delta(settings, "refresh")
    return UserTokenPair(
        access_token=_create_user_token(user, "access", settings),
        refresh_token=_create_user_token(user, "refresh", settings),
        expires_in=_expires_in_seconds(access_delta),
        refresh_expires_in=_expires_in_seconds(refresh_delta),
    )


def _create_auth_response(user: UserIdentity, settings: Settings) -> UserAuthResponse:
    token_pair = _create_user_token_pair(user, settings)
    return UserAuthResponse(
        user=_read_user(user),
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        token_type=token_pair.token_type,
        expires_in=token_pair.expires_in,
        refresh_expires_in=token_pair.refresh_expires_in,
    )


def _decode_user_token(
    token: str,
    token_type: UserTokenType,
    settings: Settings,
) -> dict[str, Any]:
    _ensure_user_auth_configured(settings)

    try:
        payload = jwt.decode(
            token,
            settings.user_token_secret,
            algorithms=[settings.user_token_algorithm],
            options={"require": ["exp", "iat", "sub", "token_version", "type"]},
        )
    except InvalidTokenError:
        raise _invalid_token_error(token_type) from None

    if not isinstance(payload, dict) or payload.get("type") != token_type:
        raise _invalid_token_error(token_type)

    return payload


def _user_from_record(record: Mapping[str, object]) -> UserRecord:
    return UserRecord(
        id=cast(UUID, record["id"]),
        first_name=cast(str, record["first_name"]),
        last_name=cast(str, record["last_name"]),
        email=cast(str, record["email"]),
        password_hash=cast(str, record["password_hash"]),
        is_active=cast(bool, record["is_active"]),
        token_version=cast(int, record["token_version"]),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


async def _get_user_by_email(pool: asyncpg.Pool, email: str) -> UserRecord | None:
    record = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {USER_COLUMNS}
            FROM users
            WHERE email = $1
            """,
            _normalize_email(email),
        ),
    )
    return _user_from_record(record) if record is not None else None


async def _get_user_by_id(pool: asyncpg.Pool, user_id: UUID) -> UserRecord | None:
    record = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {USER_COLUMNS}
            FROM users
            WHERE id = $1
            """,
            user_id,
        ),
    )
    return _user_from_record(record) if record is not None else None


async def _get_user_from_token_payload(
    pool: asyncpg.Pool,
    payload: dict[str, Any],
    token_type: UserTokenType,
) -> UserRecord:
    try:
        user_id = UUID(str(payload["sub"]))
        token_version = int(payload["token_version"])
    except (KeyError, TypeError, ValueError):
        raise _invalid_token_error(token_type) from None

    user = await _get_user_by_id(pool, user_id)
    if user is None or not user.is_active or user.token_version != token_version:
        raise _invalid_token_error(token_type)

    return user


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    pool: DbPool,
) -> UserIdentity:
    if credentials is None:
        raise _auth_error()

    payload = _decode_user_token(credentials.credentials, "access", settings)
    return await _get_user_from_token_payload(pool, payload, "access")


RequireAuth = Annotated[UserIdentity, Depends(get_current_user)]


@router.post("/signup", response_model=UserAuthResponse, status_code=status.HTTP_201_CREATED)
async def signup_user(
    payload: UserSignupRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    pool: DbPool,
) -> UserAuthResponse:
    _ensure_user_auth_configured(settings)

    try:
        record = cast(
            Mapping[str, object] | None,
            await pool.fetchrow(
                f"""
                INSERT INTO users (
                    first_name,
                    last_name,
                    email,
                    password_hash
                )
                VALUES ($1, $2, $3, $4)
                RETURNING {USER_COLUMNS}
                """,
                payload.first_name,
                payload.last_name,
                _normalize_email(str(payload.email)),
                hash_password(payload.password),
            ),
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        ) from None

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create user",
        )

    return _create_auth_response(_user_from_record(record), settings)


@router.post("/sign-in", response_model=UserAuthResponse, include_in_schema=False)
@router.post("/login", response_model=UserAuthResponse)
async def login_user(
    payload: UserLoginRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    pool: DbPool,
) -> UserAuthResponse:
    _ensure_user_auth_configured(settings)

    user = await _get_user_by_email(pool, str(payload.email))
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise _auth_error("Invalid email or password")

    await pool.execute(
        """
        UPDATE users
        SET last_login_at = now()
        WHERE id = $1
        """,
        user.id,
    )
    return _create_auth_response(user, settings)


@router.post("/refresh", response_model=UserAuthResponse)
async def refresh_user_token(
    payload: UserRefreshRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    pool: DbPool,
) -> UserAuthResponse:
    token_payload = _decode_user_token(payload.refresh_token, "refresh", settings)
    user = await _get_user_from_token_payload(pool, token_payload, "refresh")
    await pool.execute(
        """
        UPDATE users
        SET last_refresh_at = now()
        WHERE id = $1
        """,
        user.id,
    )
    return _create_auth_response(user, settings)
