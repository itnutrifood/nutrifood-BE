from datetime import datetime
from decimal import Decimal
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

from backend.apps.common.enums import LanguageCode, SubscriptionPlanStatus
from backend.apps.common.pagination import Page

SubscriptionPlanSlug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]
LocalizedShortTextValue = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
LocalizedLongTextValue = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000),
]
SubscriptionPlanInfoItem = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
SubscriptionPlanPrice = Annotated[
    Decimal,
    Field(ge=Decimal("0"), max_digits=10, decimal_places=2),
]
SortOrder = Annotated[int, Field(ge=0, le=2_147_483_647)]


class LocalizedText(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    hy_am: LocalizedShortTextValue = Field(alias="HY-AM")
    en_us: LocalizedShortTextValue = Field(alias="EN-US")
    ru_ru: LocalizedShortTextValue = Field(alias="RU-RU")

    def to_db(self) -> dict[str, str]:
        return {
            LanguageCode.HY_AM.value: self.hy_am,
            LanguageCode.EN_US.value: self.en_us,
            LanguageCode.RU_RU.value: self.ru_ru,
        }

    @model_serializer(mode="plain")
    def serialize_model(self) -> dict[str, str]:
        return self.to_db()


class OptionalLocalizedText(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    hy_am: LocalizedLongTextValue | None = Field(default=None, alias="HY-AM")
    en_us: LocalizedLongTextValue | None = Field(default=None, alias="EN-US")
    ru_ru: LocalizedLongTextValue | None = Field(default=None, alias="RU-RU")

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


class LocalizedInfoItems(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    hy_am: list[SubscriptionPlanInfoItem] | None = Field(
        default=None,
        alias="HY-AM",
        min_length=1,
        max_length=50,
    )
    en_us: list[SubscriptionPlanInfoItem] | None = Field(
        default=None,
        alias="EN-US",
        min_length=1,
        max_length=50,
    )
    ru_ru: list[SubscriptionPlanInfoItem] | None = Field(
        default=None,
        alias="RU-RU",
        min_length=1,
        max_length=50,
    )

    def to_db(self) -> dict[str, list[str]]:
        values: dict[str, list[str] | None] = {
            LanguageCode.HY_AM.value: self.hy_am,
            LanguageCode.EN_US.value: self.en_us,
            LanguageCode.RU_RU.value: self.ru_ru,
        }
        return {language: value for language, value in values.items() if value is not None}

    @model_serializer(mode="plain")
    def serialize_model(self) -> dict[str, list[str]]:
        return self.to_db()


class SubscriptionPlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: SubscriptionPlanSlug
    name: LocalizedText
    description: OptionalLocalizedText = Field(default_factory=OptionalLocalizedText)
    price: SubscriptionPlanPrice
    billing_interval: LocalizedText
    meal_count_label: OptionalLocalizedText = Field(default_factory=OptionalLocalizedText)
    is_popular: bool = False
    status: SubscriptionPlanStatus = SubscriptionPlanStatus.ACTIVE
    sort_order: SortOrder = 0
    additional_info: LocalizedInfoItems = Field(default_factory=LocalizedInfoItems)


class SubscriptionPlanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: SubscriptionPlanSlug | None = None
    name: LocalizedText | None = None
    description: OptionalLocalizedText | None = None
    price: SubscriptionPlanPrice | None = None
    billing_interval: LocalizedText | None = None
    meal_count_label: OptionalLocalizedText | None = None
    is_popular: bool | None = None
    status: SubscriptionPlanStatus | None = None
    sort_order: SortOrder | None = None
    additional_info: LocalizedInfoItems | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")

        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")

        return self


class SubscriptionPlanRead(BaseModel):
    id: UUID
    slug: str
    name: LocalizedText
    description: OptionalLocalizedText
    price: Decimal
    billing_interval: LocalizedText
    meal_count_label: OptionalLocalizedText
    is_popular: bool
    status: SubscriptionPlanStatus
    sort_order: int
    additional_info: LocalizedInfoItems
    created_at: datetime
    updated_at: datetime


class SubscriptionPlanListResponse(Page[SubscriptionPlanRead]):
    pass


class PublicSubscriptionPlanRead(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str | None
    price: Decimal
    billing_interval: str
    meal_count_label: str | None
    is_popular: bool
    status: SubscriptionPlanStatus
    sort_order: int
    additional_info: list[str]
    created_at: datetime
    updated_at: datetime
