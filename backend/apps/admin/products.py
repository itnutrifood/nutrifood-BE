import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Self, cast
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import status as http_status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_serializer,
    model_validator,
)

from backend.apps.common.enums import LanguageCode
from backend.apps.common.pagination import Page, page_count, page_offset
from backend.config.database import get_pool

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
DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]

MAX_PRODUCT_IMAGES = 8

PRODUCT_COLUMNS = """
    p.id,
    p.slug,
    p.title,
    p.description,
    p.images,
    p.image_tags,
    p.text_tags,
    p.serving_size,
    p.readiness_time_minutes,
    p.price,
    p.allergens,
    p.allergen_information,
    p.storage_delivery,
    p.created_at,
    p.updated_at,
    (
        SELECT COALESCE(array_agg(pc.category_id ORDER BY pc.category_id), ARRAY[]::uuid[])
        FROM product_categories AS pc
        WHERE pc.product_id = p.id
    ) AS category_ids
"""


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


class ProductNotFoundError(Exception):
    pass


class DuplicateProductSlugError(Exception):
    pass


class ProductCategoryNotFoundError(Exception):
    pass


router = APIRouter(prefix="/products", tags=["admin:products"])


def _json_object(value: object) -> dict[str, object]:
    if isinstance(value, str):
        loaded_value = json.loads(value)
    elif isinstance(value, Mapping):
        loaded_value = dict(value)
    else:
        raise ValueError("Expected a JSON object")

    if not isinstance(loaded_value, dict):
        raise ValueError("Expected a JSON object")

    return cast(dict[str, object], loaded_value)


def _json_array(value: object) -> list[object]:
    if isinstance(value, str):
        loaded_value = json.loads(value)
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        loaded_value = list(value)
    else:
        raise ValueError("Expected a JSON array")

    if not isinstance(loaded_value, list):
        raise ValueError("Expected a JSON array")

    return cast(list[object], loaded_value)


def _validate_unique_image_urls(images: Sequence[ProductImage]) -> None:
    urls = [image.url for image in images]
    if len(urls) != len(set(urls)):
        raise ValueError("images cannot contain duplicate urls")


def _validate_unique_category_ids(category_ids: Sequence[UUID]) -> None:
    if len(category_ids) != len(set(category_ids)):
        raise ValueError("category_ids cannot contain duplicates")


def _localized_text_db_value(value: OptionalLocalizedText | None) -> dict[str, str]:
    return value.to_db() if value is not None else {}


def _localized_words_db_value(value: LocalizedWords | None) -> dict[str, list[str]]:
    return value.to_db() if value is not None else {}


def _product_images_db_value(images: Sequence[ProductImage]) -> list[dict[str, int | str]]:
    return [image.to_db() for image in images]


def _category_ids_from_record(value: object) -> list[UUID]:
    if value is None:
        return []
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [cast(UUID, item) for item in value]
    raise ValueError("Expected a UUID array")


def _product_from_record(record: Mapping[str, object]) -> ProductRead:
    return ProductRead(
        id=cast(UUID, record["id"]),
        slug=cast(str | None, record["slug"]),
        title=LocalizedText.model_validate(_json_object(record["title"])),
        description=LocalizedText.model_validate(_json_object(record["description"])),
        images=[ProductImage.model_validate(item) for item in _json_array(record["images"])],
        category_ids=_category_ids_from_record(record["category_ids"]),
        image_tags=LocalizedWords.model_validate(_json_object(record["image_tags"])),
        text_tags=LocalizedWords.model_validate(_json_object(record["text_tags"])),
        serving_size=OptionalLocalizedText.model_validate(_json_object(record["serving_size"])),
        readiness_time_minutes=cast(int | None, record["readiness_time_minutes"]),
        price=cast(Decimal, record["price"]),
        allergens=LocalizedWords.model_validate(_json_object(record["allergens"])),
        allergen_information=OptionalLocalizedText.model_validate(
            _json_object(record["allergen_information"])
        ),
        storage_delivery=OptionalLocalizedText.model_validate(
            _json_object(record["storage_delivery"])
        ),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


def _rows_affected(command_status: str) -> int:
    try:
        return int(command_status.rsplit(maxsplit=1)[-1])
    except (IndexError, ValueError):
        return 0


async def _product_exists(pool: asyncpg.Pool, product_id: UUID) -> bool:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            "SELECT EXISTS(SELECT 1 FROM products WHERE id = $1) AS exists",
            product_id,
        ),
    )
    return bool(row and row["exists"])


async def _ensure_categories_exist(pool: asyncpg.Pool, category_ids: Sequence[UUID]) -> None:
    if not category_ids:
        return

    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            "SELECT id FROM categories WHERE id = ANY($1::uuid[])",
            list(category_ids),
        ),
    )
    existing_category_ids = {cast(UUID, row["id"]) for row in rows}
    if existing_category_ids != set(category_ids):
        raise ProductCategoryNotFoundError


async def create_product(pool: asyncpg.Pool, payload: ProductCreate) -> ProductRead:
    await _ensure_categories_exist(pool, payload.category_ids)

    try:
        row = cast(
            Mapping[str, object] | None,
            await pool.fetchrow(
                f"""
                WITH inserted_product AS (
                    INSERT INTO products (
                        slug,
                        title,
                        description,
                        images,
                        image_tags,
                        text_tags,
                        serving_size,
                        readiness_time_minutes,
                        price,
                        allergens,
                        allergen_information,
                        storage_delivery
                    )
                    VALUES (
                        $1,
                        $2::jsonb,
                        $3::jsonb,
                        $4::jsonb,
                        $5::jsonb,
                        $6::jsonb,
                        $7::jsonb,
                        $8,
                        $9,
                        $10::jsonb,
                        $11::jsonb,
                        $12::jsonb
                    )
                    RETURNING *
                ),
                inserted_categories AS (
                    INSERT INTO product_categories (product_id, category_id)
                    SELECT inserted_product.id, category_id
                    FROM inserted_product
                    CROSS JOIN unnest($13::uuid[]) AS category_id
                    RETURNING category_id
                )
                SELECT {PRODUCT_COLUMNS}
                FROM inserted_product AS p
                """,
                payload.slug,
                json.dumps(payload.title.to_db()),
                json.dumps(payload.description.to_db()),
                json.dumps(_product_images_db_value(payload.images)),
                json.dumps(payload.image_tags.to_db()),
                json.dumps(payload.text_tags.to_db()),
                json.dumps(payload.serving_size.to_db()),
                payload.readiness_time_minutes,
                payload.price,
                json.dumps(payload.allergens.to_db()),
                json.dumps(payload.allergen_information.to_db()),
                json.dumps(payload.storage_delivery.to_db()),
                payload.category_ids,
            ),
        )
    except asyncpg.UniqueViolationError as exc:
        raise DuplicateProductSlugError from exc
    except asyncpg.ForeignKeyViolationError as exc:
        raise ProductCategoryNotFoundError from exc

    if row is None:
        raise RuntimeError("Product insert did not return a row")

    return _product_from_record(row)


async def get_product(pool: asyncpg.Pool, product_id: UUID) -> ProductRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {PRODUCT_COLUMNS}
            FROM products AS p
            WHERE p.id = $1
            """,
            product_id,
        ),
    )
    if row is None:
        raise ProductNotFoundError

    return _product_from_record(row)


async def list_products(
    pool: asyncpg.Pool,
    category_id: UUID | None,
    page: int,
    limit: int,
) -> ProductListResponse:
    conditions: list[str] = []
    params: list[Any] = []

    if category_id is not None:
        params.append(category_id)
        conditions.append(
            """
            EXISTS (
                SELECT 1
                FROM product_categories AS pc
                WHERE pc.product_id = p.id
                    AND pc.category_id = $1
            )
            """
        )

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    count_row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(f"SELECT count(*) AS total FROM products AS p {where_clause}", *params),
    )
    total = cast(int, count_row["total"]) if count_row is not None else 0

    offset = page_offset(page, limit)
    params.extend([limit, offset])
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {PRODUCT_COLUMNS}
            FROM products AS p
            {where_clause}
            ORDER BY p.created_at DESC, p.id
            LIMIT ${len(params) - 1}
            OFFSET ${len(params)}
            """,
            *params,
        ),
    )

    return ProductListResponse(
        items=[_product_from_record(row) for row in rows],
        total=total,
        page=page,
        limit=limit,
        total_pages=page_count(total, limit),
    )


async def update_product(
    pool: asyncpg.Pool,
    product_id: UUID,
    payload: ProductUpdate,
) -> ProductRead:
    category_ids_were_set = "category_ids" in payload.model_fields_set
    if category_ids_were_set:
        if payload.category_ids is None:
            raise ValueError("category_ids cannot be null")
        await _ensure_categories_exist(pool, payload.category_ids)

    assignments: list[str] = []
    params: list[Any] = [product_id]

    if "slug" in payload.model_fields_set:
        params.append(payload.slug)
        assignments.append(f"slug = ${len(params)}")

    if "title" in payload.model_fields_set:
        if payload.title is None:
            raise ValueError("title cannot be null")
        params.append(json.dumps(payload.title.to_db()))
        assignments.append(f"title = ${len(params)}::jsonb")

    if "description" in payload.model_fields_set:
        if payload.description is None:
            raise ValueError("description cannot be null")
        params.append(json.dumps(payload.description.to_db()))
        assignments.append(f"description = ${len(params)}::jsonb")

    if "images" in payload.model_fields_set:
        if payload.images is None:
            raise ValueError("images cannot be null")
        params.append(json.dumps(_product_images_db_value(payload.images)))
        assignments.append(f"images = ${len(params)}::jsonb")

    if "image_tags" in payload.model_fields_set:
        params.append(json.dumps(_localized_words_db_value(payload.image_tags)))
        assignments.append(f"image_tags = ${len(params)}::jsonb")

    if "text_tags" in payload.model_fields_set:
        params.append(json.dumps(_localized_words_db_value(payload.text_tags)))
        assignments.append(f"text_tags = ${len(params)}::jsonb")

    if "serving_size" in payload.model_fields_set:
        params.append(json.dumps(_localized_text_db_value(payload.serving_size)))
        assignments.append(f"serving_size = ${len(params)}::jsonb")

    if "readiness_time_minutes" in payload.model_fields_set:
        params.append(payload.readiness_time_minutes)
        assignments.append(f"readiness_time_minutes = ${len(params)}")

    if "price" in payload.model_fields_set:
        if payload.price is None:
            raise ValueError("price cannot be null")
        params.append(payload.price)
        assignments.append(f"price = ${len(params)}")

    if "allergens" in payload.model_fields_set:
        params.append(json.dumps(_localized_words_db_value(payload.allergens)))
        assignments.append(f"allergens = ${len(params)}::jsonb")

    if "allergen_information" in payload.model_fields_set:
        params.append(json.dumps(_localized_text_db_value(payload.allergen_information)))
        assignments.append(f"allergen_information = ${len(params)}::jsonb")

    if "storage_delivery" in payload.model_fields_set:
        params.append(json.dumps(_localized_text_db_value(payload.storage_delivery)))
        assignments.append(f"storage_delivery = ${len(params)}::jsonb")

    selected_product_statement = "SELECT id FROM products WHERE id = $1"
    if assignments:
        selected_product_statement = f"""
            UPDATE products
            SET {", ".join(assignments)}
            WHERE id = $1
            RETURNING id
        """

    category_ctes = ""
    if category_ids_were_set:
        params.append(cast(list[UUID], payload.category_ids))
        category_ids_param = len(params)
        category_ctes = f"""
            ,
            deleted_categories AS (
                DELETE FROM product_categories
                WHERE product_id = (SELECT id FROM selected_product)
                RETURNING category_id
            ),
            inserted_categories AS (
                INSERT INTO product_categories (product_id, category_id)
                SELECT selected_product.id, category_id
                FROM selected_product
                CROSS JOIN unnest(${category_ids_param}::uuid[]) AS category_id
                RETURNING category_id
            )
        """

    try:
        row = cast(
            Mapping[str, object] | None,
            await pool.fetchrow(
                f"""
                WITH selected_product AS (
                    {selected_product_statement}
                )
                {category_ctes}
                SELECT {PRODUCT_COLUMNS}
                FROM products AS p
                WHERE p.id = (SELECT id FROM selected_product)
                """,
                *params,
            ),
        )
    except asyncpg.UniqueViolationError as exc:
        raise DuplicateProductSlugError from exc
    except asyncpg.ForeignKeyViolationError as exc:
        raise ProductCategoryNotFoundError from exc

    if row is None:
        raise ProductNotFoundError

    return _product_from_record(row)


async def delete_product(pool: asyncpg.Pool, product_id: UUID) -> None:
    command_status = cast(str, await pool.execute("DELETE FROM products WHERE id = $1", product_id))

    if _rows_affected(command_status) == 0:
        raise ProductNotFoundError


def _raise_product_http_error(exc: Exception) -> None:
    if isinstance(exc, ProductNotFoundError):
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        ) from exc
    if isinstance(exc, ProductCategoryNotFoundError):
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Product category not found",
        ) from exc
    if isinstance(exc, DuplicateProductSlugError):
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Product slug already exists",
        ) from exc

    raise exc


@router.post(
    "",
    response_model=ProductRead,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_admin_product(
    payload: ProductCreate,
    pool: DbPool,
) -> ProductRead:
    try:
        return await create_product(pool, payload)
    except Exception as exc:
        _raise_product_http_error(exc)
        raise


@router.get("", response_model=ProductListResponse)
async def list_admin_products(
    pool: DbPool,
    category_id: UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ProductListResponse:
    return await list_products(
        pool=pool,
        category_id=category_id,
        page=page,
        limit=limit,
    )


@router.get("/{product_id}", response_model=ProductRead)
async def read_admin_product(
    product_id: UUID,
    pool: DbPool,
) -> ProductRead:
    try:
        return await get_product(pool, product_id)
    except Exception as exc:
        _raise_product_http_error(exc)
        raise


@router.patch("/{product_id}", response_model=ProductRead)
async def update_admin_product(
    product_id: UUID,
    payload: ProductUpdate,
    pool: DbPool,
) -> ProductRead:
    try:
        return await update_product(pool, product_id, payload)
    except Exception as exc:
        _raise_product_http_error(exc)
        raise


@router.delete("/{product_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_admin_product(
    product_id: UUID,
    pool: DbPool,
) -> Response:
    try:
        await delete_product(pool, product_id)
    except Exception as exc:
        _raise_product_http_error(exc)
        raise

    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
