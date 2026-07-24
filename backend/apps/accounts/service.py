from collections.abc import Mapping
from typing import Any

import asyncpg

from backend.apps.accounts import repository
from backend.apps.accounts.exceptions import (
    AccountConflictError,
    AuthenticationError,
    AuthorizationError,
    UserWriteConflictError,
)
from backend.apps.accounts.models import FirebaseIdentity
from backend.apps.accounts.schemas import UserIdentity, UserRecord
from backend.config.settings import Settings


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


def firebase_identity_from_claims(
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
        raise AuthenticationError("Invalid Firebase ID token")
    if sign_in_provider not in settings.firebase_allowed_sign_in_providers:
        raise AuthorizationError("Sign-in provider is not allowed")

    email_verified = claims.get("email_verified") is True
    if settings.firebase_require_verified_email and not email_verified:
        raise AuthorizationError("Email verification is required")

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


def identity_from_user(
    user: UserRecord,
    firebase_identity: FirebaseIdentity,
) -> UserIdentity:
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


async def get_or_create_user(
    pool: asyncpg.Pool,
    identity: FirebaseIdentity,
) -> UserRecord:
    user = await repository.get_user_by_firebase_uid(pool, identity.uid)
    if user is not None:
        return await repository.sync_user_profile(pool, user, identity)

    user = await repository.get_user_by_email(pool, identity.email)
    if user is not None:
        if not user.is_active:
            raise AuthorizationError("User account is disabled")
        if not identity.email_verified:
            raise AuthorizationError("Email verification is required to link an existing account")
        if user.firebase_uid:
            raise AccountConflictError("Email is already linked to another Firebase account")
        return await repository.link_legacy_user(pool, user, identity)

    try:
        return await repository.create_user(pool, identity)
    except UserWriteConflictError:
        concurrent_user = await repository.get_user_by_firebase_uid(pool, identity.uid)
        if concurrent_user is not None:
            return concurrent_user
        raise AccountConflictError("Email is already linked to another Firebase account") from None
