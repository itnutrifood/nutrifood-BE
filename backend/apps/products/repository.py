import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import asyncpg

from backend.apps.common.db import json_array, json_object, rows_affected
from backend.apps.common.enums import CategoryStatus, LanguageCode
from backend.apps.common.pagination import page_count, page_offset
from backend.apps.products.exceptions import (
    DuplicateProductSlugError,
    ProductCategoryNotFoundError,
    ProductNotFoundError,
)
from backend.apps.products.schemas import (
    LocalizedText,
    LocalizedWords,
    OptionalLocalizedText,
    ProductCreate,
    ProductImage,
    ProductListResponse,
    ProductRead,
    ProductUpdate,
)

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


@dataclass(frozen=True)
class ProductSearchConfiguration:
    title_key: str
    vector_column: str
    text_search_configuration: str


@dataclass(frozen=True)
class ProductSearchPosition:
    exact_title_rank: int
    title_match_rank: int
    search_rank: Decimal
    created_at: datetime
    id: UUID


@dataclass(frozen=True)
class ProductSearchResult:
    product: ProductRead
    position: ProductSearchPosition


PRODUCT_SEARCH_CONFIGURATIONS: Mapping[LanguageCode, ProductSearchConfiguration] = {
    LanguageCode.HY_AM: ProductSearchConfiguration(
        title_key=LanguageCode.HY_AM.value,
        vector_column="search_vector_hy_am",
        text_search_configuration="pg_catalog.armenian",
    ),
    LanguageCode.EN_US: ProductSearchConfiguration(
        title_key=LanguageCode.EN_US.value,
        vector_column="search_vector_en_us",
        text_search_configuration="pg_catalog.english",
    ),
    LanguageCode.RU_RU: ProductSearchConfiguration(
        title_key=LanguageCode.RU_RU.value,
        vector_column="search_vector_ru_ru",
        text_search_configuration="pg_catalog.russian",
    ),
}


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


def product_from_record(record: Mapping[str, object]) -> ProductRead:
    return ProductRead(
        id=cast(UUID, record["id"]),
        slug=cast(str | None, record["slug"]),
        title=LocalizedText.model_validate(json_object(record["title"])),
        description=LocalizedText.model_validate(json_object(record["description"])),
        images=[ProductImage.model_validate(item) for item in json_array(record["images"])],
        category_ids=_category_ids_from_record(record["category_ids"]),
        image_tags=LocalizedWords.model_validate(json_object(record["image_tags"])),
        text_tags=LocalizedWords.model_validate(json_object(record["text_tags"])),
        serving_size=OptionalLocalizedText.model_validate(json_object(record["serving_size"])),
        readiness_time_minutes=cast(int | None, record["readiness_time_minutes"]),
        price=cast(Decimal, record["price"]),
        allergens=LocalizedWords.model_validate(json_object(record["allergens"])),
        allergen_information=OptionalLocalizedText.model_validate(
            json_object(record["allergen_information"])
        ),
        storage_delivery=OptionalLocalizedText.model_validate(
            json_object(record["storage_delivery"])
        ),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


async def categories_exist(pool: asyncpg.Pool, category_ids: Sequence[UUID]) -> bool:
    if not category_ids:
        return True

    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            "SELECT id FROM categories WHERE id = ANY($1::uuid[])",
            list(category_ids),
        ),
    )
    existing_category_ids = {cast(UUID, row["id"]) for row in rows}
    return existing_category_ids == set(category_ids)


async def create_product(pool: asyncpg.Pool, payload: ProductCreate) -> ProductRead:
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

    return product_from_record(row)


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

    return product_from_record(row)


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

    params.extend([limit, page_offset(page, limit)])
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
        items=[product_from_record(row) for row in rows],
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
    assignments: list[str] = []
    params: list[Any] = [product_id]

    if "slug" in payload.model_fields_set:
        params.append(payload.slug)
        assignments.append(f"slug = ${len(params)}")
    if "title" in payload.model_fields_set:
        params.append(json.dumps(cast(LocalizedText, payload.title).to_db()))
        assignments.append(f"title = ${len(params)}::jsonb")
    if "description" in payload.model_fields_set:
        params.append(json.dumps(cast(LocalizedText, payload.description).to_db()))
        assignments.append(f"description = ${len(params)}::jsonb")
    if "images" in payload.model_fields_set:
        params.append(
            json.dumps(_product_images_db_value(cast(list[ProductImage], payload.images)))
        )
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

    return product_from_record(row)


async def delete_product(pool: asyncpg.Pool, product_id: UUID) -> None:
    command_status = cast(str, await pool.execute("DELETE FROM products WHERE id = $1", product_id))
    if rows_affected(command_status) == 0:
        raise ProductNotFoundError


async def list_public_products(
    pool: asyncpg.Pool,
    category_id: UUID | None,
    limit: int,
    cursor: tuple[datetime, UUID] | None,
) -> list[ProductRead]:
    params: list[object] = []
    conditions: list[str] = []

    if category_id is not None:
        params.append(category_id)
        category_id_param = len(params)
        params.append(CategoryStatus.ACTIVE.value)
        status_param = len(params)
        conditions.append(
            f"""
            EXISTS (
                SELECT 1
                FROM product_categories AS pc
                INNER JOIN categories AS c ON c.id = pc.category_id
                WHERE pc.product_id = p.id
                    AND pc.category_id = ${category_id_param}
                    AND c.status = ${status_param}::category_status
            )
            """
        )

    if cursor is not None:
        params.extend(cursor)
        created_at_param = len(params) - 1
        id_param = len(params)
        conditions.append(
            f"""
            (
                p.created_at < ${created_at_param}
                OR (p.created_at = ${created_at_param} AND p.id > ${id_param})
            )
            """
        )

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit + 1)
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {PRODUCT_COLUMNS}
            FROM products AS p
            {where_clause}
            ORDER BY p.created_at DESC, p.id
            LIMIT ${len(params)}
            """,
            *params,
        ),
    )
    return [product_from_record(row) for row in rows]


async def search_public_products(
    pool: asyncpg.Pool,
    language: LanguageCode,
    search: str,
    category_id: UUID | None,
    limit: int,
    cursor: ProductSearchPosition | None,
) -> list[ProductSearchResult]:
    configuration = PRODUCT_SEARCH_CONFIGURATIONS[language]
    params: list[object] = [search]
    conditions = [f"p.{configuration.vector_column} @@ search_query.query"]

    if category_id is not None:
        params.append(category_id)
        category_id_param = len(params)
        params.append(CategoryStatus.ACTIVE.value)
        status_param = len(params)
        conditions.append(
            f"""
            EXISTS (
                SELECT 1
                FROM product_categories AS pc
                INNER JOIN categories AS c ON c.id = pc.category_id
                WHERE pc.product_id = p.id
                    AND pc.category_id = ${category_id_param}
                    AND c.status = ${status_param}::category_status
            )
            """
        )

    cursor_where_clause = ""
    if cursor is not None:
        params.extend(
            [
                cursor.exact_title_rank,
                cursor.title_match_rank,
                cursor.search_rank,
                cursor.created_at,
                cursor.id,
            ]
        )
        exact_title_param = len(params) - 4
        title_match_param = len(params) - 3
        search_rank_param = len(params) - 2
        created_at_param = len(params) - 1
        id_param = len(params)
        cursor_where_clause = f"""
            WHERE p.exact_title_rank < ${exact_title_param}
                OR (
                    p.exact_title_rank = ${exact_title_param}
                    AND p.title_match_rank < ${title_match_param}
                )
                OR (
                    p.exact_title_rank = ${exact_title_param}
                    AND p.title_match_rank = ${title_match_param}
                    AND p.search_rank < ${search_rank_param}
                )
                OR (
                    p.exact_title_rank = ${exact_title_param}
                    AND p.title_match_rank = ${title_match_param}
                    AND p.search_rank = ${search_rank_param}
                    AND p.created_at < ${created_at_param}
                )
                OR (
                    p.exact_title_rank = ${exact_title_param}
                    AND p.title_match_rank = ${title_match_param}
                    AND p.search_rank = ${search_rank_param}
                    AND p.created_at = ${created_at_param}
                    AND p.id > ${id_param}
                )
        """

    params.append(limit + 1)
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            WITH search_query AS (
                SELECT websearch_to_tsquery(
                    '{configuration.text_search_configuration}'::regconfig,
                    $1
                ) AS query
            ),
            ranked_products AS (
                SELECT
                    {PRODUCT_COLUMNS},
                    CASE
                        WHEN lower(btrim(COALESCE(p.title ->> '{configuration.title_key}', '')))
                            = lower($1)
                        THEN 1
                        ELSE 0
                    END AS exact_title_rank,
                    CASE
                        WHEN to_tsvector(
                            '{configuration.text_search_configuration}'::regconfig,
                            COALESCE(p.title ->> '{configuration.title_key}', '')
                        ) @@ search_query.query
                        THEN 1
                        ELSE 0
                    END AS title_match_rank,
                    round(
                        ts_rank_cd(
                            p.{configuration.vector_column},
                            search_query.query,
                            32
                        )::numeric,
                        6
                    ) AS search_rank
                FROM products AS p
                CROSS JOIN search_query
                WHERE {" AND ".join(conditions)}
            )
            SELECT *
            FROM ranked_products AS p
            {cursor_where_clause}
            ORDER BY
                p.exact_title_rank DESC,
                p.title_match_rank DESC,
                p.search_rank DESC,
                p.created_at DESC,
                p.id
            LIMIT ${len(params)}
            """,
            *params,
        ),
    )

    return [
        ProductSearchResult(
            product=product_from_record(row),
            position=ProductSearchPosition(
                exact_title_rank=cast(int, row["exact_title_rank"]),
                title_match_rank=cast(int, row["title_match_rank"]),
                search_rank=cast(Decimal, row["search_rank"]),
                created_at=cast(datetime, row["created_at"]),
                id=cast(UUID, row["id"]),
            ),
        )
        for row in rows
    ]


async def get_public_product(pool: asyncpg.Pool, product_id: UUID) -> ProductRead:
    return await get_product(pool, product_id)
