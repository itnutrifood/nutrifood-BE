import asyncpg

from backend.apps.common.enums import LanguageCode
from backend.apps.common.localization import required_localized_text
from backend.apps.ingredients import repository
from backend.apps.ingredients.schemas import IngredientRead, PublicIngredientRead


def _to_public_ingredient(
    ingredient: IngredientRead,
    language: LanguageCode,
) -> PublicIngredientRead:
    return PublicIngredientRead(
        id=ingredient.id,
        name=required_localized_text(ingredient.name.to_db(), language),
    )


async def list_public_ingredients(
    pool: asyncpg.Pool,
    language: LanguageCode,
) -> list[PublicIngredientRead]:
    ingredients = await repository.list_all_ingredients(pool, language)
    return [_to_public_ingredient(ingredient, language) for ingredient in ingredients]
