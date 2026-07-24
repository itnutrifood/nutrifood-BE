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

from backend.apps.common.enums import EmploymentType, LanguageCode, OpenPositionStatus
from backend.apps.common.pagination import Page

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
DescriptionText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)
]


class LocalizedShortText(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    hy_am: ShortText = Field(alias="HY-AM")
    en_us: ShortText = Field(alias="EN-US")
    ru_ru: ShortText = Field(alias="RU-RU")

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

    hy_am: DescriptionText = Field(alias="HY-AM")
    en_us: DescriptionText = Field(alias="EN-US")
    ru_ru: DescriptionText = Field(alias="RU-RU")

    def to_db(self) -> dict[str, str]:
        return {
            LanguageCode.HY_AM.value: self.hy_am,
            LanguageCode.EN_US.value: self.en_us,
            LanguageCode.RU_RU.value: self.ru_ru,
        }

    @model_serializer(mode="plain")
    def serialize_model(self) -> dict[str, str]:
        return self.to_db()


class OpenPositionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: LocalizedShortText
    employment_type: EmploymentType
    description: LocalizedDescription
    position: LocalizedShortText
    city: LocalizedShortText
    status: OpenPositionStatus = OpenPositionStatus.ACTIVE


class OpenPositionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: LocalizedShortText | None = None
    employment_type: EmploymentType | None = None
    description: LocalizedDescription | None = None
    position: LocalizedShortText | None = None
    city: LocalizedShortText | None = None
    status: OpenPositionStatus | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class OpenPositionRead(BaseModel):
    id: UUID
    title: LocalizedShortText
    employment_type: EmploymentType
    description: LocalizedDescription
    position: LocalizedShortText
    city: LocalizedShortText
    status: OpenPositionStatus
    created_at: datetime
    updated_at: datetime


class OpenPositionListResponse(Page[OpenPositionRead]):
    pass


class PublicOpenPositionRead(BaseModel):
    id: UUID
    title: str
    employment_type: EmploymentType
    description: str
    position: str
    city: str
    created_at: datetime
    updated_at: datetime
