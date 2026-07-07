from fastapi import APIRouter

from backend.apps.accounts.auth import RequireAuth, UserRead
from backend.apps.accounts.auth import router as auth_router

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: RequireAuth) -> UserRead:
    return UserRead(
        id=current_user.id,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        email=current_user.email,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
    )


router.include_router(auth_router, prefix="/auth")
