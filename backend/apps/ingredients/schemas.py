from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_serializer,
    model_validator,
)

from backend.apps.common.enums import LanguageCode
from backend.apps.common.pagination import Page

IngredientNameValue = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]


class LocalizedIngredientName(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    hy_am: IngredientNameValue = Field(alias="HY-AM")
    en_us: IngredientNameValue = Field(alias="EN-US")
    ru_ru: IngredientNameValue = Field(alias="RU-RU")

    def to_db(self) -> dict[str, str]:
        return {
            LanguageCode.HY_AM.value: self.hy_am,
            LanguageCode.EN_US.value: self.en_us,
            LanguageCode.RU_RU.value: self.ru_ru,
        }

    @model_serializer(mode="plain")
    def serialize_model(self) -> dict[str, str]:
        return self.to_db()


class IngredientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: LocalizedIngredientName


class IngredientUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: LocalizedIngredientName | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if self.name is None:
            raise ValueError("name cannot be null")
        return self


class IngredientRead(BaseModel):
    id: UUID
    name: LocalizedIngredientName
    created_at: datetime
    updated_at: datetime


class IngredientListResponse(Page[IngredientRead]):
    pass
