from typing import Annotated

from fastapi import APIRouter, Depends, Request

from backend.apps.admin.auth_rate_limit import enforce_admin_login_rate_limit
from backend.apps.admin.auth_schemas import (
    AdminLoginRequest,
    AdminRefreshRequest,
    AdminTokenPair,
)
from backend.apps.admin.auth_service import (
    login_admin as login_admin_service,
)
from backend.apps.admin.auth_service import (
    logout_admin as logout_admin_service,
)
from backend.apps.admin.auth_service import (
    refresh_admin_token as refresh_admin_token_service,
)
from backend.config.cache import CacheClient
from backend.config.database import DbPool
from backend.config.settings import Settings, get_settings

router = APIRouter(prefix="/auth", tags=["admin:auth"])


@router.post("/sign-in", response_model=AdminTokenPair, include_in_schema=False)
@router.post("/login", response_model=AdminTokenPair)
async def login_admin(
    payload: AdminLoginRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    pool: DbPool,
    cache: CacheClient,
    request: Request,
) -> AdminTokenPair:
    source = request.client.host if request.client is not None else "unknown"
    await enforce_admin_login_rate_limit(cache, payload.identifier, source)
    return await login_admin_service(pool, payload, settings)


@router.post("/refresh", response_model=AdminTokenPair)
async def refresh_admin_token(
    payload: AdminRefreshRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    pool: DbPool,
) -> AdminTokenPair:
    return await refresh_admin_token_service(pool, payload.refresh_token, settings)


@router.post("/logout", status_code=204)
async def logout_admin(
    payload: AdminRefreshRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    pool: DbPool,
) -> None:
    await logout_admin_service(pool, payload.refresh_token, settings)
