from fastapi import APIRouter

from backend.apps.accounts.dependencies import RequireAuth
from backend.apps.accounts.schemas import UserRead

router = APIRouter(tags=["accounts:auth"])


@router.post("/session", response_model=UserRead)
async def create_firebase_session(current_user: RequireAuth) -> UserRead:
    """Verify a Firebase ID token and synchronize its local user profile."""
    return UserRead.model_validate(current_user, from_attributes=True)
