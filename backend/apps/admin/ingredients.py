"""Compatibility exports for ingredient administration."""

from backend.apps.ingredients.admin_routers import router
from backend.apps.ingredients.admin_service import (
    create_ingredient,
    delete_ingredient,
    get_ingredient,
    list_ingredients,
    update_ingredient,
)
from backend.apps.ingredients.exceptions import (
    DuplicateIngredientNameError,
    IngredientNotFoundError,
)
from backend.apps.ingredients.repository import INGREDIENT_COLUMNS
from backend.apps.ingredients.repository import ingredient_from_record as _ingredient_from_record
from backend.apps.ingredients.schemas import (
    IngredientCreate,
    IngredientListResponse,
    IngredientNameValue,
    IngredientRead,
    IngredientUpdate,
    LocalizedIngredientName,
)
from backend.config.database import DbPool

__all__ = [
    "INGREDIENT_COLUMNS",
    "DbPool",
    "DuplicateIngredientNameError",
    "IngredientCreate",
    "IngredientListResponse",
    "IngredientNameValue",
    "IngredientNotFoundError",
    "IngredientRead",
    "IngredientUpdate",
    "LocalizedIngredientName",
    "_ingredient_from_record",
    "create_ingredient",
    "delete_ingredient",
    "get_ingredient",
    "list_ingredients",
    "router",
    "update_ingredient",
]
