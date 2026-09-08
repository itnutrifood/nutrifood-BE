from collections.abc import Sequence
from uuid import UUID


class PreferenceIngredientNotFoundError(Exception):
    def __init__(self, ingredient_ids: Sequence[UUID]) -> None:
        self.ingredient_ids = list(ingredient_ids)
        super().__init__("One or more ingredients were not found")
