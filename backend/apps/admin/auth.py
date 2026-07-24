"""Compatibility exports for admin authentication."""

from backend.apps.admin.auth_routers import login_admin, refresh_admin_token, router
from backend.apps.admin.auth_schemas import (
    AdminLoginRequest,
    AdminRecord,
    AdminRefreshRequest,
    AdminTokenPair,
    AdminUser,
)
from backend.apps.admin.auth_service import AdminTokenType
from backend.apps.admin.dependencies import RequireAdminAuth, admin_auth
from backend.config.database import DbPool

__all__ = [
    "AdminLoginRequest",
    "AdminRecord",
    "AdminRefreshRequest",
    "AdminTokenPair",
    "AdminTokenType",
    "AdminUser",
    "DbPool",
    "RequireAdminAuth",
    "admin_auth",
    "login_admin",
    "refresh_admin_token",
    "router",
]
