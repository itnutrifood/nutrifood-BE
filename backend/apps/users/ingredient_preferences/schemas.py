from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_INGREDIENT_PREFERENCES = 1_000


class IngredientPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    whitelisted_ingredient_ids: list[UUID] = Field(max_length=MAX_INGREDIENT_PREFERENCES)
    blacklisted_ingredient_ids: list[UUID] = Field(max_length=MAX_INGREDIENT_PREFERENCES)

    @model_validator(mode="after")
    def validate_ingredient_ids(self) -> Self:
        whitelisted_ids = set(self.whitelisted_ingredient_ids)
        blacklisted_ids = set(self.blacklisted_ingredient_ids)

        if len(whitelisted_ids) != len(self.whitelisted_ingredient_ids):
            raise ValueError("whitelisted_ingredient_ids cannot contain duplicates")
        if len(blacklisted_ids) != len(self.blacklisted_ingredient_ids):
            raise ValueError("blacklisted_ingredient_ids cannot contain duplicates")

        overlapping_ids = whitelisted_ids.intersection(blacklisted_ids)
        if overlapping_ids:
            raise ValueError("The same ingredient cannot be both whitelisted and blacklisted")
        if len(whitelisted_ids) + len(blacklisted_ids) > MAX_INGREDIENT_PREFERENCES:
            raise ValueError(
                f"No more than {MAX_INGREDIENT_PREFERENCES} ingredient preferences are allowed"
            )
        return self
