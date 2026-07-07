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

from backend.apps.common.enums import LanguageCode, SubscriptionPlanStatus
from backend.apps.common.pagination import Page, page_count, page_offset
from backend.config.database import get_pool

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
DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]

SUBSCRIPTION_PLAN_COLUMNS = """
    id,
    slug,
    name,
    description,
    price,
    billing_interval,
    meal_count_label,
    is_popular,
    status::text AS status,
    sort_order,
    additional_info,
    created_at,
    updated_at
"""


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


class SubscriptionPlanNotFoundError(Exception):
    pass


class DuplicateSubscriptionPlanSlugError(Exception):
    pass


router = APIRouter(prefix="/subscriptions", tags=["admin:subscriptions"])


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


def _optional_localized_text_db_value(value: OptionalLocalizedText | None) -> dict[str, str]:
    return value.to_db() if value is not None else {}


def _localized_info_items_db_value(value: LocalizedInfoItems | None) -> dict[str, list[str]]:
    return value.to_db() if value is not None else {}


def _subscription_plan_from_record(record: Mapping[str, object]) -> SubscriptionPlanRead:
    return SubscriptionPlanRead(
        id=cast(UUID, record["id"]),
        slug=cast(str, record["slug"]),
        name=LocalizedText.model_validate(_json_object(record["name"])),
        description=OptionalLocalizedText.model_validate(_json_object(record["description"])),
        price=cast(Decimal, record["price"]),
        billing_interval=LocalizedText.model_validate(_json_object(record["billing_interval"])),
        meal_count_label=OptionalLocalizedText.model_validate(
            _json_object(record["meal_count_label"])
        ),
        is_popular=cast(bool, record["is_popular"]),
        status=SubscriptionPlanStatus(cast(str, record["status"])),
        sort_order=cast(int, record["sort_order"]),
        additional_info=LocalizedInfoItems.model_validate(_json_object(record["additional_info"])),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


def _rows_affected(command_status: str) -> int:
    try:
        return int(command_status.rsplit(maxsplit=1)[-1])
    except (IndexError, ValueError):
        return 0


async def create_subscription_plan(
    pool: asyncpg.Pool,
    payload: SubscriptionPlanCreate,
) -> SubscriptionPlanRead:
    try:
        row = cast(
            Mapping[str, object] | None,
            await pool.fetchrow(
                f"""
                INSERT INTO subscription_plans (
                    slug,
                    name,
                    description,
                    price,
                    billing_interval,
                    meal_count_label,
                    is_popular,
                    status,
                    sort_order,
                    additional_info
                )
                VALUES (
                    $1,
                    $2::jsonb,
                    $3::jsonb,
                    $4,
                    $5::jsonb,
                    $6::jsonb,
                    $7,
                    $8::subscription_plan_status,
                    $9,
                    $10::jsonb
                )
                RETURNING {SUBSCRIPTION_PLAN_COLUMNS}
                """,
                payload.slug,
                json.dumps(payload.name.to_db()),
                json.dumps(payload.description.to_db()),
                payload.price,
                json.dumps(payload.billing_interval.to_db()),
                json.dumps(payload.meal_count_label.to_db()),
                payload.is_popular,
                payload.status.value,
                payload.sort_order,
                json.dumps(payload.additional_info.to_db()),
            ),
        )
    except asyncpg.UniqueViolationError as exc:
        raise DuplicateSubscriptionPlanSlugError from exc

    if row is None:
        raise RuntimeError("Subscription plan insert did not return a row")

    return _subscription_plan_from_record(row)


async def get_subscription_plan(
    pool: asyncpg.Pool,
    subscription_plan_id: UUID,
) -> SubscriptionPlanRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {SUBSCRIPTION_PLAN_COLUMNS}
            FROM subscription_plans
            WHERE id = $1
            """,
            subscription_plan_id,
        ),
    )
    if row is None:
        raise SubscriptionPlanNotFoundError

    return _subscription_plan_from_record(row)


async def list_subscription_plans(
    pool: asyncpg.Pool,
    status_filter: SubscriptionPlanStatus | None,
    is_popular: bool | None,
    page: int,
    limit: int,
) -> SubscriptionPlanListResponse:
    conditions: list[str] = []
    params: list[Any] = []

    if status_filter is not None:
        params.append(status_filter.value)
        conditions.append(f"status = ${len(params)}::subscription_plan_status")

    if is_popular is not None:
        params.append(is_popular)
        conditions.append(f"is_popular = ${len(params)}")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    count_row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"SELECT count(*) AS total FROM subscription_plans {where_clause}",
            *params,
        ),
    )
    total = cast(int, count_row["total"]) if count_row is not None else 0

    offset = page_offset(page, limit)
    params.extend([limit, offset])
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {SUBSCRIPTION_PLAN_COLUMNS}
            FROM subscription_plans
            {where_clause}
            ORDER BY sort_order, price, slug
            LIMIT ${len(params) - 1}
            OFFSET ${len(params)}
            """,
            *params,
        ),
    )

    return SubscriptionPlanListResponse(
        items=[_subscription_plan_from_record(row) for row in rows],
        total=total,
        page=page,
        limit=limit,
        total_pages=page_count(total, limit),
    )


async def update_subscription_plan(
    pool: asyncpg.Pool,
    subscription_plan_id: UUID,
    payload: SubscriptionPlanUpdate,
) -> SubscriptionPlanRead:
    assignments: list[str] = []
    params: list[Any] = []

    if "slug" in payload.model_fields_set:
        params.append(payload.slug)
        assignments.append(f"slug = ${len(params)}")

    if "name" in payload.model_fields_set:
        if payload.name is None:
            raise ValueError("name cannot be null")
        params.append(json.dumps(payload.name.to_db()))
        assignments.append(f"name = ${len(params)}::jsonb")

    if "description" in payload.model_fields_set:
        params.append(json.dumps(_optional_localized_text_db_value(payload.description)))
        assignments.append(f"description = ${len(params)}::jsonb")

    if "price" in payload.model_fields_set:
        params.append(payload.price)
        assignments.append(f"price = ${len(params)}")

    if "billing_interval" in payload.model_fields_set:
        if payload.billing_interval is None:
            raise ValueError("billing_interval cannot be null")
        params.append(json.dumps(payload.billing_interval.to_db()))
        assignments.append(f"billing_interval = ${len(params)}::jsonb")

    if "meal_count_label" in payload.model_fields_set:
        params.append(json.dumps(_optional_localized_text_db_value(payload.meal_count_label)))
        assignments.append(f"meal_count_label = ${len(params)}::jsonb")

    if "is_popular" in payload.model_fields_set:
        params.append(payload.is_popular)
        assignments.append(f"is_popular = ${len(params)}")

    if "status" in payload.model_fields_set:
        params.append(cast(SubscriptionPlanStatus, payload.status).value)
        assignments.append(f"status = ${len(params)}::subscription_plan_status")

    if "sort_order" in payload.model_fields_set:
        params.append(payload.sort_order)
        assignments.append(f"sort_order = ${len(params)}")

    if "additional_info" in payload.model_fields_set:
        params.append(json.dumps(_localized_info_items_db_value(payload.additional_info)))
        assignments.append(f"additional_info = ${len(params)}::jsonb")

    params.append(subscription_plan_id)

    try:
        row = cast(
            Mapping[str, object] | None,
            await pool.fetchrow(
                f"""
                UPDATE subscription_plans
                SET {", ".join(assignments)}
                WHERE id = ${len(params)}
                RETURNING {SUBSCRIPTION_PLAN_COLUMNS}
                """,
                *params,
            ),
        )
    except asyncpg.UniqueViolationError as exc:
        raise DuplicateSubscriptionPlanSlugError from exc

    if row is None:
        raise SubscriptionPlanNotFoundError

    return _subscription_plan_from_record(row)


async def delete_subscription_plan(pool: asyncpg.Pool, subscription_plan_id: UUID) -> None:
    command_status = cast(
        str,
        await pool.execute("DELETE FROM subscription_plans WHERE id = $1", subscription_plan_id),
    )

    if _rows_affected(command_status) == 0:
        raise SubscriptionPlanNotFoundError


def _raise_subscription_plan_http_error(exc: Exception) -> None:
    if isinstance(exc, SubscriptionPlanNotFoundError):
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Subscription plan not found",
        ) from exc
    if isinstance(exc, DuplicateSubscriptionPlanSlugError):
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Subscription plan slug already exists",
        ) from exc

    raise exc


@router.post(
    "",
    response_model=SubscriptionPlanRead,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_admin_subscription_plan(
    payload: SubscriptionPlanCreate,
    pool: DbPool,
) -> SubscriptionPlanRead:
    try:
        return await create_subscription_plan(pool, payload)
    except Exception as exc:
        _raise_subscription_plan_http_error(exc)
        raise


@router.get("", response_model=SubscriptionPlanListResponse)
async def list_admin_subscription_plans(
    pool: DbPool,
    status_filter: Annotated[SubscriptionPlanStatus | None, Query(alias="status")] = None,
    is_popular: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> SubscriptionPlanListResponse:
    return await list_subscription_plans(
        pool=pool,
        status_filter=status_filter,
        is_popular=is_popular,
        page=page,
        limit=limit,
    )


@router.get("/{subscription_plan_id}", response_model=SubscriptionPlanRead)
async def read_admin_subscription_plan(
    subscription_plan_id: UUID,
    pool: DbPool,
) -> SubscriptionPlanRead:
    try:
        return await get_subscription_plan(pool, subscription_plan_id)
    except Exception as exc:
        _raise_subscription_plan_http_error(exc)
        raise


@router.patch("/{subscription_plan_id}", response_model=SubscriptionPlanRead)
async def update_admin_subscription_plan(
    subscription_plan_id: UUID,
    payload: SubscriptionPlanUpdate,
    pool: DbPool,
) -> SubscriptionPlanRead:
    try:
        return await update_subscription_plan(pool, subscription_plan_id, payload)
    except Exception as exc:
        _raise_subscription_plan_http_error(exc)
        raise


@router.delete("/{subscription_plan_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_admin_subscription_plan(
    subscription_plan_id: UUID,
    pool: DbPool,
) -> Response:
    try:
        await delete_subscription_plan(pool, subscription_plan_id)
    except Exception as exc:
        _raise_subscription_plan_http_error(exc)
        raise

    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
