"""Compatibility exports for authentication dependencies and schemas."""

from backend.apps.accounts.auth_routers import router
from backend.apps.accounts.dependencies import RequireAuth, RoleChecker, get_current_user
from backend.apps.accounts.models import FirebaseIdentity
from backend.apps.accounts.schemas import UserIdentity, UserRead, UserRecord
from backend.config.database import DbPool

__all__ = [
    "RequireAuth",
    "RoleChecker",
    "DbPool",
    "FirebaseIdentity",
    "UserIdentity",
    "UserRead",
    "UserRecord",
    "get_current_user",
    "router",
]
