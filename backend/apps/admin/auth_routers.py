from typing import Annotated

from fastapi import APIRouter, Depends

from backend.apps.admin.auth_schemas import (
    AdminLoginRequest,
    AdminRefreshRequest,
    AdminTokenPair,
)
from backend.apps.admin.auth_service import (
    login_admin as login_admin_service,
)
from backend.apps.admin.auth_service import (
    refresh_admin_token as refresh_admin_token_service,
)
from backend.config.database import DbPool
from backend.config.settings import Settings, get_settings

router = APIRouter(prefix="/auth", tags=["admin:auth"])


@router.post("/sign-in", response_model=AdminTokenPair, include_in_schema=False)
@router.post("/login", response_model=AdminTokenPair)
async def login_admin(
    payload: AdminLoginRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    pool: DbPool,
) -> AdminTokenPair:
    return await login_admin_service(pool, payload, settings)


@router.post("/refresh", response_model=AdminTokenPair)
async def refresh_admin_token(
    payload: AdminRefreshRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    pool: DbPool,
) -> AdminTokenPair:
    return await refresh_admin_token_service(pool, payload.refresh_token, settings)
