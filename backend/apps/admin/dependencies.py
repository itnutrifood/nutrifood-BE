from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.apps.admin.auth_exceptions import AdminAuthenticationError
from backend.apps.admin.auth_schemas import AdminUser
from backend.apps.admin.auth_service import authenticate_admin_access
from backend.config.database import DbPool
from backend.config.settings import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False)


async def admin_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    pool: DbPool,
) -> AdminUser:
    if credentials is None:
        raise AdminAuthenticationError
    return await authenticate_admin_access(pool, credentials.credentials, settings)


RequireAdminAuth = Annotated[AdminUser, Depends(admin_auth)]
