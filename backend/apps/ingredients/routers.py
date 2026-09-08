from fastapi import APIRouter

from backend.apps.common.localization import LocaleFromPath
from backend.apps.ingredients.schemas import PublicIngredientRead
from backend.apps.ingredients.service import list_public_ingredients
from backend.config.database import DbPool

router = APIRouter(prefix="/ingredients", tags=["ingredients"])


@router.get("", response_model=list[PublicIngredientRead])
async def list_ingredients(
    language: LocaleFromPath,
    pool: DbPool,
) -> list[PublicIngredientRead]:
    return await list_public_ingredients(pool, language)
