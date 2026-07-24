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

from backend.apps.common.enums import FAQStatus, LanguageCode
from backend.apps.common.pagination import Page

FAQSlug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]
QuestionValue = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
AnswerValue = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000),
]
SortOrder = Annotated[int, Field(ge=0, le=2_147_483_647)]


class LocalizedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    hy_am: QuestionValue = Field(alias="HY-AM")
    en_us: QuestionValue = Field(alias="EN-US")
    ru_ru: QuestionValue = Field(alias="RU-RU")

    def to_db(self) -> dict[str, str]:
        return {
            LanguageCode.HY_AM.value: self.hy_am,
            LanguageCode.EN_US.value: self.en_us,
            LanguageCode.RU_RU.value: self.ru_ru,
        }

    @model_serializer(mode="plain")
    def serialize_model(self) -> dict[str, str]:
        return self.to_db()


class LocalizedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    hy_am: AnswerValue = Field(alias="HY-AM")
    en_us: AnswerValue = Field(alias="EN-US")
    ru_ru: AnswerValue = Field(alias="RU-RU")

    def to_db(self) -> dict[str, str]:
        return {
            LanguageCode.HY_AM.value: self.hy_am,
            LanguageCode.EN_US.value: self.en_us,
            LanguageCode.RU_RU.value: self.ru_ru,
        }

    @model_serializer(mode="plain")
    def serialize_model(self) -> dict[str, str]:
        return self.to_db()


class FAQCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: FAQSlug
    question: LocalizedQuestion
    answer: LocalizedAnswer
    status: FAQStatus = FAQStatus.ACTIVE
    sort_order: SortOrder = 0


class FAQUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: FAQSlug | None = None
    question: LocalizedQuestion | None = None
    answer: LocalizedAnswer | None = None
    status: FAQStatus | None = None
    sort_order: SortOrder | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")

        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")

        return self


class FAQRead(BaseModel):
    id: UUID
    slug: str
    question: LocalizedQuestion
    answer: LocalizedAnswer
    status: FAQStatus
    sort_order: int
    created_at: datetime
    updated_at: datetime


class FAQListResponse(Page[FAQRead]):
    pass


class PublicFAQRead(BaseModel):
    id: UUID
    slug: str
    question: str
    answer: str
    sort_order: int
    created_at: datetime
    updated_at: datetime
