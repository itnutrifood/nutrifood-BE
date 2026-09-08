from fastapi import APIRouter

from backend.apps.accounts.dependencies import RequireAuth
from backend.apps.users.ingredient_preferences.schemas import IngredientPreferences
from backend.apps.users.ingredient_preferences.service import (
    get_ingredient_preferences,
    replace_ingredient_preferences,
)
from backend.config.database import DbPool

router = APIRouter(prefix="/ingredient-preferences", tags=["ingredient-preferences"])


@router.get("", response_model=IngredientPreferences)
async def read_ingredient_preferences(
    current_user: RequireAuth,
    pool: DbPool,
) -> IngredientPreferences:
    return await get_ingredient_preferences(pool, current_user.id)


@router.put("", response_model=IngredientPreferences)
async def set_ingredient_preferences(
    preferences: IngredientPreferences,
    current_user: RequireAuth,
    pool: DbPool,
) -> IngredientPreferences:
    return await replace_ingredient_preferences(pool, current_user.id, preferences)
