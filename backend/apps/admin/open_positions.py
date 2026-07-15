import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Annotated, Any, NoReturn, Self, cast
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

from backend.apps.common.enums import EmploymentType, LanguageCode, OpenPositionStatus
from backend.apps.common.pagination import Page, page_count, page_offset
from backend.config.database import get_pool

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
DescriptionText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)
]
DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]

OPEN_POSITION_COLUMNS = """
    id,
    title,
    employment_type::text AS employment_type,
    description,
    position,
    city,
    status::text AS status,
    created_at,
    updated_at
"""


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


class OpenPositionNotFoundError(Exception):
    pass


router = APIRouter(prefix="/open-positions", tags=["admin:open-positions"])


def _json_object(value: object) -> dict[str, object]:
    loaded = (
        json.loads(value)
        if isinstance(value, str)
        else dict(value)
        if isinstance(value, Mapping)
        else None
    )
    if not isinstance(loaded, dict):
        raise ValueError("Expected a JSON object")
    return cast(dict[str, object], loaded)


def _open_position_from_record(record: Mapping[str, object]) -> OpenPositionRead:
    return OpenPositionRead(
        id=cast(UUID, record["id"]),
        title=LocalizedShortText.model_validate(_json_object(record["title"])),
        employment_type=EmploymentType(cast(str, record["employment_type"])),
        description=LocalizedDescription.model_validate(_json_object(record["description"])),
        position=LocalizedShortText.model_validate(_json_object(record["position"])),
        city=LocalizedShortText.model_validate(_json_object(record["city"])),
        status=OpenPositionStatus(cast(str, record["status"])),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


async def create_open_position(pool: asyncpg.Pool, payload: OpenPositionCreate) -> OpenPositionRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            INSERT INTO open_positions
                (title, employment_type, description, position, city, status)
            VALUES ($1::jsonb, $2::employment_type, $3::jsonb, $4::jsonb, $5::jsonb,
                    $6::open_position_status)
            RETURNING {OPEN_POSITION_COLUMNS}
            """,
            json.dumps(payload.title.to_db()),
            payload.employment_type.value,
            json.dumps(payload.description.to_db()),
            json.dumps(payload.position.to_db()),
            json.dumps(payload.city.to_db()),
            payload.status.value,
        ),
    )
    if row is None:
        raise RuntimeError("Open position insert did not return a row")
    return _open_position_from_record(row)


async def get_open_position(pool: asyncpg.Pool, open_position_id: UUID) -> OpenPositionRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"SELECT {OPEN_POSITION_COLUMNS} FROM open_positions WHERE id = $1",
            open_position_id,
        ),
    )
    if row is None:
        raise OpenPositionNotFoundError
    return _open_position_from_record(row)


async def list_open_positions(
    pool: asyncpg.Pool,
    status_filter: OpenPositionStatus | None,
    employment_type_filter: EmploymentType | None,
    page: int,
    limit: int,
) -> OpenPositionListResponse:
    params: list[object] = []
    conditions: list[str] = []
    if status_filter is not None:
        params.append(status_filter.value)
        conditions.append(f"status = ${len(params)}::open_position_status")
    if employment_type_filter is not None:
        params.append(employment_type_filter.value)
        conditions.append(f"employment_type = ${len(params)}::employment_type")
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    count_row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"SELECT count(*) AS total FROM open_positions {where_clause}", *params
        ),
    )
    total = cast(int, count_row["total"]) if count_row is not None else 0
    params.extend([limit, page_offset(page, limit)])
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {OPEN_POSITION_COLUMNS}
            FROM open_positions
            {where_clause}
            ORDER BY created_at DESC, id
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """,
            *params,
        ),
    )
    return OpenPositionListResponse(
        items=[_open_position_from_record(row) for row in rows],
        total=total,
        page=page,
        limit=limit,
        total_pages=page_count(total, limit),
    )


async def update_open_position(
    pool: asyncpg.Pool, open_position_id: UUID, payload: OpenPositionUpdate
) -> OpenPositionRead:
    assignments: list[str] = []
    params: list[Any] = []
    localized_fields: dict[str, LocalizedShortText | LocalizedDescription | None] = {
        "title": payload.title,
        "description": payload.description,
        "position": payload.position,
        "city": payload.city,
    }
    for field_name, value in localized_fields.items():
        if field_name in payload.model_fields_set:
            params.append(
                json.dumps(cast(LocalizedShortText | LocalizedDescription, value).to_db())
            )
            assignments.append(f"{field_name} = ${len(params)}::jsonb")
    if "employment_type" in payload.model_fields_set:
        params.append(cast(EmploymentType, payload.employment_type).value)
        assignments.append(f"employment_type = ${len(params)}::employment_type")
    if "status" in payload.model_fields_set:
        params.append(cast(OpenPositionStatus, payload.status).value)
        assignments.append(f"status = ${len(params)}::open_position_status")
    params.append(open_position_id)
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            UPDATE open_positions SET {", ".join(assignments)}
            WHERE id = ${len(params)} RETURNING {OPEN_POSITION_COLUMNS}
            """,
            *params,
        ),
    )
    if row is None:
        raise OpenPositionNotFoundError
    return _open_position_from_record(row)


async def delete_open_position(pool: asyncpg.Pool, open_position_id: UUID) -> None:
    result = cast(
        str, await pool.execute("DELETE FROM open_positions WHERE id = $1", open_position_id)
    )
    try:
        affected = int(result.rsplit(maxsplit=1)[-1])
    except (IndexError, ValueError):
        affected = 0
    if affected == 0:
        raise OpenPositionNotFoundError


def _raise_not_found(exc: OpenPositionNotFoundError) -> NoReturn:
    raise HTTPException(
        status_code=http_status.HTTP_404_NOT_FOUND, detail="Open position not found"
    ) from exc


@router.post("", response_model=OpenPositionRead, status_code=http_status.HTTP_201_CREATED)
async def create_admin_open_position(payload: OpenPositionCreate, pool: DbPool) -> OpenPositionRead:
    return await create_open_position(pool, payload)


@router.get("", response_model=OpenPositionListResponse)
async def list_admin_open_positions(
    pool: DbPool,
    status_filter: Annotated[OpenPositionStatus | None, Query(alias="status")] = None,
    employment_type_filter: Annotated[EmploymentType | None, Query(alias="employment_type")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> OpenPositionListResponse:
    return await list_open_positions(pool, status_filter, employment_type_filter, page, limit)


@router.get("/{open_position_id}", response_model=OpenPositionRead)
async def read_admin_open_position(open_position_id: UUID, pool: DbPool) -> OpenPositionRead:
    try:
        return await get_open_position(pool, open_position_id)
    except OpenPositionNotFoundError as exc:
        _raise_not_found(exc)


@router.patch("/{open_position_id}", response_model=OpenPositionRead)
async def update_admin_open_position(
    open_position_id: UUID, payload: OpenPositionUpdate, pool: DbPool
) -> OpenPositionRead:
    try:
        return await update_open_position(pool, open_position_id, payload)
    except OpenPositionNotFoundError as exc:
        _raise_not_found(exc)


@router.delete("/{open_position_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_admin_open_position(open_position_id: UUID, pool: DbPool) -> Response:
    try:
        await delete_open_position(pool, open_position_id)
    except OpenPositionNotFoundError as exc:
        _raise_not_found(exc)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
