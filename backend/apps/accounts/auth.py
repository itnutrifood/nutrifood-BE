from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, cast
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth
from firebase_admin.exceptions import FirebaseError
from pydantic import BaseModel, EmailStr

from backend.config.database import get_pool
from backend.config.firebase import FirebaseService, get_firebase_service
from backend.config.settings import Settings, get_settings

DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]

USER_COLUMNS = """
    id,
    firebase_uid,
    first_name,
    last_name,
    email,
    is_active,
    created_at,
    updated_at
"""


class UserRead(BaseModel):
    id: UUID
    first_name: str | None
    last_name: str | None
    email: EmailStr
    created_at: datetime
    updated_at: datetime


class UserIdentity(UserRead):
    firebase_uid: str
    sign_in_provider: str
    roles: frozenset[str]


class UserRecord(UserRead):
    firebase_uid: str | None
    is_active: bool


@dataclass(frozen=True)
class FirebaseIdentity:
    uid: str
    email: str
    email_verified: bool
    first_name: str | None
    last_name: str | None
    sign_in_provider: str
    roles: frozenset[str]


bearer_scheme = HTTPBearer(auto_error=False)
router = APIRouter(tags=["accounts:auth"])


def _auth_error(detail: str = "Authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden_error(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _claim_string(claims: Mapping[str, Any], key: str) -> str | None:
    value = claims.get(key)
    if not isinstance(value, str):
        return None
    stripped_value = value.strip()
    return stripped_value or None


def _name_claims(claims: Mapping[str, Any]) -> tuple[str | None, str | None]:
    first_name = _claim_string(claims, "given_name")
    last_name = _claim_string(claims, "family_name")
    if first_name is not None or last_name is not None:
        return first_name, last_name

    display_name = _claim_string(claims, "name")
    if display_name is None:
        return None, None

    name_parts = display_name.split(maxsplit=1)
    return name_parts[0], name_parts[1] if len(name_parts) == 2 else None


def _roles_from_claims(claims: Mapping[str, Any]) -> frozenset[str]:
    role_claim = claims.get("roles", ())
    if isinstance(role_claim, str):
        roles = [role_claim]
    elif isinstance(role_claim, list) and all(isinstance(role, str) for role in role_claim):
        roles = role_claim
    else:
        return frozenset()

    return frozenset(role.strip() for role in roles if role.strip())


def _firebase_identity_from_claims(
    claims: Mapping[str, Any],
    settings: Settings,
) -> FirebaseIdentity:
    uid = _claim_string(claims, "uid") or _claim_string(claims, "sub")
    email = _claim_string(claims, "email")
    firebase_claim = claims.get("firebase")
    sign_in_provider = (
        _claim_string(firebase_claim, "sign_in_provider")
        if isinstance(firebase_claim, Mapping)
        else None
    )

    if uid is None or email is None or sign_in_provider is None:
        raise _auth_error("Invalid Firebase ID token")

    if sign_in_provider not in settings.firebase_allowed_sign_in_providers:
        raise _forbidden_error("Sign-in provider is not allowed")

    email_verified = claims.get("email_verified") is True
    if settings.firebase_require_verified_email and not email_verified:
        raise _forbidden_error("Email verification is required")

    first_name, last_name = _name_claims(claims)
    return FirebaseIdentity(
        uid=uid,
        email=email.lower(),
        email_verified=email_verified,
        first_name=first_name,
        last_name=last_name,
        sign_in_provider=sign_in_provider,
        roles=_roles_from_claims(claims),
    )


def _user_from_record(record: Mapping[str, object]) -> UserRecord:
    return UserRecord(
        id=cast(UUID, record["id"]),
        firebase_uid=cast(str | None, record["firebase_uid"]),
        first_name=cast(str | None, record["first_name"]),
        last_name=cast(str | None, record["last_name"]),
        email=cast(str, record["email"]),
        is_active=cast(bool, record["is_active"]),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


def _identity_from_user(user: UserRecord, firebase_identity: FirebaseIdentity) -> UserIdentity:
    if user.firebase_uid is None:
        raise RuntimeError("Authenticated user must have a Firebase UID")
    return UserIdentity(
        id=user.id,
        firebase_uid=user.firebase_uid,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        sign_in_provider=firebase_identity.sign_in_provider,
        roles=firebase_identity.roles,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def _get_user_by_firebase_uid(pool: asyncpg.Pool, uid: str) -> UserRecord | None:
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
    return _user_from_record(record) if record is not None else None


async def _get_user_by_email(pool: asyncpg.Pool, email: str) -> UserRecord | None:
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
    return _user_from_record(record) if record is not None else None


async def _link_legacy_user(
    pool: asyncpg.Pool,
    user: UserRecord,
    identity: FirebaseIdentity,
) -> UserRecord:
    if user.firebase_uid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already linked to another Firebase account",
        )

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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Firebase account is already linked",
        ) from None

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Account linking conflict",
        )
    return _user_from_record(record)


async def _create_user(pool: asyncpg.Pool, identity: FirebaseIdentity) -> UserRecord:
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
                    password_hash,
                    last_login_at
                )
                VALUES ($1, $2, $3, $4, NULL, now())
                RETURNING {USER_COLUMNS}
                """,
                identity.uid,
                identity.first_name,
                identity.last_name,
                identity.email,
            ),
        )
    except asyncpg.UniqueViolationError:
        # A concurrent first request may have created the row after our reads.
        concurrent_user = await _get_user_by_firebase_uid(pool, identity.uid)
        if concurrent_user is not None:
            return concurrent_user
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already linked to another Firebase account",
        ) from None

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create user",
        )
    return _user_from_record(record)


async def _sync_user_profile(
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already linked to another Firebase account",
        ) from None

    return _user_from_record(record) if record is not None else user


async def _get_or_create_user(
    pool: asyncpg.Pool,
    identity: FirebaseIdentity,
) -> UserRecord:
    user = await _get_user_by_firebase_uid(pool, identity.uid)
    if user is not None:
        return await _sync_user_profile(pool, user, identity)

    user = await _get_user_by_email(pool, identity.email)
    if user is not None:
        if not user.is_active:
            raise _forbidden_error("User account is disabled")
        if not identity.email_verified:
            raise _forbidden_error("Email verification is required to link an existing account")
        return await _link_legacy_user(pool, user, identity)

    return await _create_user(pool, identity)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    firebase_service: Annotated[FirebaseService, Depends(get_firebase_service)],
    pool: DbPool,
) -> UserIdentity:
    if credentials is None:
        raise _auth_error()

    try:
        claims = await firebase_service.verify_id_token(credentials.credentials)
    except (
        auth.ExpiredIdTokenError,
        auth.RevokedIdTokenError,
        auth.UserDisabledError,
        auth.UserNotFoundError,
    ):
        raise _auth_error("Firebase session is no longer valid") from None
    except auth.InvalidIdTokenError:
        raise _auth_error("Invalid Firebase ID token") from None
    except (FirebaseError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase authentication is temporarily unavailable",
        ) from None

    firebase_identity = _firebase_identity_from_claims(claims, settings)
    user = await _get_or_create_user(pool, firebase_identity)
    if not user.is_active:
        raise _forbidden_error("User account is disabled")
    return _identity_from_user(user, firebase_identity)


RequireAuth = Annotated[UserIdentity, Depends(get_current_user)]


class RoleChecker:
    def __init__(self, *required_roles: str) -> None:
        normalized_roles = frozenset(role.strip() for role in required_roles if role.strip())
        if not normalized_roles:
            raise ValueError("At least one non-empty role is required")
        self.required_roles = normalized_roles

    async def __call__(self, current_user: RequireAuth) -> UserIdentity:
        if not self.required_roles.issubset(current_user.roles):
            raise _forbidden_error("Insufficient permissions")
        return current_user


@router.post("/session", response_model=UserRead)
async def create_firebase_session(current_user: RequireAuth) -> UserRead:
    """Verify a Firebase ID token and synchronize its local user profile."""
    return UserRead.model_validate(current_user, from_attributes=True)
