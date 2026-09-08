from fastapi import APIRouter

from backend.apps.users.addresses.routers import router as addresses_router
from backend.apps.users.ingredient_preferences.routers import (
    router as ingredient_preferences_router,
)

router = APIRouter(prefix="/users", tags=["users"])

router.include_router(addresses_router)
router.include_router(ingredient_preferences_router)
