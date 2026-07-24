from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth
from firebase_admin.exceptions import FirebaseError

from backend.apps.accounts.exceptions import (
    AuthenticationError,
    AuthenticationServiceUnavailableError,
    AuthorizationError,
)
from backend.apps.accounts.schemas import UserIdentity
from backend.apps.accounts.service import (
    firebase_identity_from_claims,
    get_or_create_user,
    identity_from_user,
)
from backend.config.database import DbPool
from backend.config.firebase import FirebaseServiceDependency
from backend.config.settings import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    firebase_service: FirebaseServiceDependency,
    pool: DbPool,
) -> UserIdentity:
    if credentials is None:
        raise AuthenticationError

    try:
        claims = await firebase_service.verify_id_token(credentials.credentials)
    except (
        auth.ExpiredIdTokenError,
        auth.RevokedIdTokenError,
        auth.UserDisabledError,
        auth.UserNotFoundError,
    ):
        raise AuthenticationError("Firebase session is no longer valid") from None
    except auth.InvalidIdTokenError:
        raise AuthenticationError("Invalid Firebase ID token") from None
    except (FirebaseError, ValueError):
        raise AuthenticationServiceUnavailableError(
            "Firebase authentication is temporarily unavailable"
        ) from None

    firebase_identity = firebase_identity_from_claims(claims, settings)
    user = await get_or_create_user(pool, firebase_identity)
    if not user.is_active:
        raise AuthorizationError("User account is disabled")
    return identity_from_user(user, firebase_identity)


RequireAuth = Annotated[UserIdentity, Depends(get_current_user)]


class RoleChecker:
    def __init__(self, *required_roles: str) -> None:
        normalized_roles = frozenset(role.strip() for role in required_roles if role.strip())
        if not normalized_roles:
            raise ValueError("At least one non-empty role is required")
        self.required_roles = normalized_roles

    async def __call__(self, current_user: RequireAuth) -> UserIdentity:
        if not self.required_roles.issubset(current_user.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
