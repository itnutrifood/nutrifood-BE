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

from backend.apps.common.enums import CategoryStatus, LanguageCode
from backend.apps.common.pagination import Page

CategorySlug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]
SortOrder = Annotated[int, Field(ge=0, le=2_147_483_647)]


class LocalizedName(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    hy_am: str = Field(alias="HY-AM", min_length=1, max_length=255)
    en_us: str = Field(alias="EN-US", min_length=1, max_length=255)
    ru_ru: str = Field(alias="RU-RU", min_length=1, max_length=255)

    def to_db(self) -> dict[str, str]:
        return {
            LanguageCode.HY_AM.value: self.hy_am,
            LanguageCode.EN_US.value: self.en_us,
            LanguageCode.RU_RU.value: self.ru_ru,
        }

    @model_serializer(mode="plain")
    def serialize_model(self) -> dict[str, str]:
        return self.to_db()


class LocalizedDescription(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    hy_am: str | None = Field(default=None, alias="HY-AM", min_length=1)
    en_us: str | None = Field(default=None, alias="EN-US", min_length=1)
    ru_ru: str | None = Field(default=None, alias="RU-RU", min_length=1)

    def to_db(self) -> dict[str, str]:
        values = {
            LanguageCode.HY_AM.value: self.hy_am,
            LanguageCode.EN_US.value: self.en_us,
            LanguageCode.RU_RU.value: self.ru_ru,
        }
        return {language: value for language, value in values.items() if value is not None}

    @model_serializer(mode="plain")
    def serialize_model(self) -> dict[str, str]:
        return self.to_db()


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_id: UUID | None = None
    slug: CategorySlug
    name: LocalizedName
    description: LocalizedDescription = Field(default_factory=LocalizedDescription)
    status: CategoryStatus = CategoryStatus.ACTIVE
    sort_order: SortOrder = 0


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_id: UUID | None = None
    slug: CategorySlug | None = None
    name: LocalizedName | None = None
    description: LocalizedDescription | None = None
    status: CategoryStatus | None = None
    sort_order: SortOrder | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")

        nullable_fields = {"parent_id"}
        for field_name in self.model_fields_set - nullable_fields:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")

        return self


class CategoryRead(BaseModel):
    id: UUID
    parent_id: UUID | None
    slug: str
    name: LocalizedName
    description: LocalizedDescription
    status: CategoryStatus
    sort_order: int
    created_at: datetime
    updated_at: datetime


class CategoryListResponse(Page[CategoryRead]):
    pass


class PublicCategoryRead(BaseModel):
    id: UUID
    parent_id: UUID | None
    slug: str
    name: str
    description: str | None
    status: CategoryStatus
    sort_order: int
    created_at: datetime
    updated_at: datetime
