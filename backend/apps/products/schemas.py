from collections.abc import Sequence
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

from backend.apps.common.enums import LanguageCode
from backend.apps.common.pagination import Page

ProductSlug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]
LocalizedTextValue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
LocalizedWord = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
]
ImageUrl = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2048),
]
ImageDimension = Annotated[int, Field(ge=1, le=4096)]
ImageSizeBytes = Annotated[int, Field(ge=1, le=5 * 1024 * 1024)]
ReadinessTimeMinutes = Annotated[int, Field(ge=1, le=24 * 60)]
ProductPrice = Annotated[Decimal, Field(ge=Decimal("0"), max_digits=10, decimal_places=2)]

MAX_PRODUCT_IMAGES = 8


class LocalizedText(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    hy_am: LocalizedTextValue = Field(alias="HY-AM")
    en_us: LocalizedTextValue = Field(alias="EN-US")
    ru_ru: LocalizedTextValue = Field(alias="RU-RU")

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

    hy_am: LocalizedTextValue | None = Field(default=None, alias="HY-AM")
    en_us: LocalizedTextValue | None = Field(default=None, alias="EN-US")
    ru_ru: LocalizedTextValue | None = Field(default=None, alias="RU-RU")

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


class LocalizedWords(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    hy_am: list[LocalizedWord] | None = Field(
        default=None,
        alias="HY-AM",
        min_length=1,
        max_length=50,
    )
    en_us: list[LocalizedWord] | None = Field(
        default=None,
        alias="EN-US",
        min_length=1,
        max_length=50,
    )
    ru_ru: list[LocalizedWord] | None = Field(
        default=None,
        alias="RU-RU",
        min_length=1,
        max_length=50,
    )

    def to_db(self) -> dict[str, list[str]]:
        values = {
            LanguageCode.HY_AM.value: self.hy_am,
            LanguageCode.EN_US.value: self.en_us,
            LanguageCode.RU_RU.value: self.ru_ru,
        }
        return {language: value for language, value in values.items() if value is not None}

    @model_serializer(mode="plain")
    def serialize_model(self) -> dict[str, list[str]]:
        return self.to_db()


class ProductImage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: ImageUrl
    width: ImageDimension | None = None
    height: ImageDimension | None = None
    size_bytes: ImageSizeBytes | None = None

    def to_db(self) -> dict[str, int | str]:
        values: dict[str, int | str] = {"url": self.url}
        if self.width is not None:
            values["width"] = self.width
        if self.height is not None:
            values["height"] = self.height
        if self.size_bytes is not None:
            values["size_bytes"] = self.size_bytes
        return values


def _validate_unique_image_urls(images: Sequence[ProductImage]) -> None:
    urls = [image.url for image in images]
    if len(urls) != len(set(urls)):
        raise ValueError("images cannot contain duplicate urls")


def _validate_unique_category_ids(category_ids: Sequence[UUID]) -> None:
    if len(category_ids) != len(set(category_ids)):
        raise ValueError("category_ids cannot contain duplicates")


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: ProductSlug | None = None
    title: LocalizedText
    description: LocalizedText
    images: list[ProductImage] = Field(min_length=1, max_length=MAX_PRODUCT_IMAGES)
    category_ids: list[UUID] = Field(default_factory=list, max_length=100)
    image_tags: LocalizedWords = Field(default_factory=LocalizedWords)
    text_tags: LocalizedWords = Field(default_factory=LocalizedWords)
    serving_size: OptionalLocalizedText = Field(default_factory=OptionalLocalizedText)
    readiness_time_minutes: ReadinessTimeMinutes | None = None
    price: ProductPrice
    allergens: LocalizedWords = Field(default_factory=LocalizedWords)
    allergen_information: OptionalLocalizedText = Field(default_factory=OptionalLocalizedText)
    storage_delivery: OptionalLocalizedText = Field(default_factory=OptionalLocalizedText)

    @model_validator(mode="after")
    def validate_unique_values(self) -> Self:
        _validate_unique_image_urls(self.images)
        _validate_unique_category_ids(self.category_ids)
        return self


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: ProductSlug | None = None
    title: LocalizedText | None = None
    description: LocalizedText | None = None
    images: list[ProductImage] | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_PRODUCT_IMAGES,
    )
    category_ids: list[UUID] | None = Field(default=None, max_length=100)
    image_tags: LocalizedWords | None = None
    text_tags: LocalizedWords | None = None
    serving_size: OptionalLocalizedText | None = None
    readiness_time_minutes: ReadinessTimeMinutes | None = None
    price: ProductPrice | None = None
    allergens: LocalizedWords | None = None
    allergen_information: OptionalLocalizedText | None = None
    storage_delivery: OptionalLocalizedText | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")

        non_nullable_fields = {"title", "description", "images", "category_ids", "price"}
        for field_name in self.model_fields_set.intersection(non_nullable_fields):
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")

        if self.images is not None:
            _validate_unique_image_urls(self.images)
        if self.category_ids is not None:
            _validate_unique_category_ids(self.category_ids)

        return self


class ProductRead(BaseModel):
    id: UUID
    slug: str | None
    title: LocalizedText
    description: LocalizedText
    images: list[ProductImage]
    category_ids: list[UUID]
    image_tags: LocalizedWords
    text_tags: LocalizedWords
    serving_size: OptionalLocalizedText
    readiness_time_minutes: int | None
    price: Decimal
    allergens: LocalizedWords
    allergen_information: OptionalLocalizedText
    storage_delivery: OptionalLocalizedText
    created_at: datetime
    updated_at: datetime


class ProductListResponse(Page[ProductRead]):
    pass


class PublicProductRead(BaseModel):
    id: UUID
    slug: str | None
    title: str
    description: str
    images: list[ProductImage]
    category_ids: list[UUID]
    image_tags: list[str]
    text_tags: list[str]
    serving_size: str | None
    readiness_time_minutes: int | None
    price: Decimal
    allergens: list[str]
    allergen_information: str | None
    storage_delivery: str | None
    created_at: datetime
    updated_at: datetime
