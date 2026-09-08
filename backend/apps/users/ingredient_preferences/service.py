from uuid import UUID

import asyncpg

from backend.apps.users.ingredient_preferences import repository
from backend.apps.users.ingredient_preferences.schemas import IngredientPreferences


async def get_ingredient_preferences(
    pool: asyncpg.Pool,
    user_id: UUID,
) -> IngredientPreferences:
    return await repository.get_ingredient_preferences(pool, user_id)


async def replace_ingredient_preferences(
    pool: asyncpg.Pool,
    user_id: UUID,
    preferences: IngredientPreferences,
) -> IngredientPreferences:
    await repository.replace_ingredient_preferences(pool, user_id, preferences)
    return IngredientPreferences(
        whitelisted_ingredient_ids=sorted(preferences.whitelisted_ingredient_ids),
        blacklisted_ingredient_ids=sorted(preferences.blacklisted_ingredient_ids),
    )
