from fastapi import APIRouter

from backend.apps.accounts.auth import RequireAuth, UserRead
from backend.apps.accounts.auth import router as auth_router

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: RequireAuth) -> UserRead:
    return UserRead.model_validate(current_user, from_attributes=True)


router.include_router(auth_router, prefix="/auth")
