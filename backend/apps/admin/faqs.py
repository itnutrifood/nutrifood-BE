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

from backend.apps.common.enums import FAQStatus, LanguageCode
from backend.apps.common.pagination import Page, page_count, page_offset
from backend.config.database import get_pool

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
DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]

FAQ_COLUMNS = """
    id,
    slug,
    question,
    answer,
    status::text AS status,
    sort_order,
    created_at,
    updated_at
"""


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


class FAQNotFoundError(Exception):
    pass


class DuplicateFAQSlugError(Exception):
    pass


router = APIRouter(prefix="/faqs", tags=["admin:faqs"])


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


def _faq_from_record(record: Mapping[str, object]) -> FAQRead:
    return FAQRead(
        id=cast(UUID, record["id"]),
        slug=cast(str, record["slug"]),
        question=LocalizedQuestion.model_validate(_json_object(record["question"])),
        answer=LocalizedAnswer.model_validate(_json_object(record["answer"])),
        status=FAQStatus(cast(str, record["status"])),
        sort_order=cast(int, record["sort_order"]),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


def _rows_affected(command_status: str) -> int:
    try:
        return int(command_status.rsplit(maxsplit=1)[-1])
    except (IndexError, ValueError):
        return 0


async def create_faq(pool: asyncpg.Pool, payload: FAQCreate) -> FAQRead:
    try:
        row = cast(
            Mapping[str, object] | None,
            await pool.fetchrow(
                f"""
                INSERT INTO faqs (slug, question, answer, status, sort_order)
                VALUES ($1, $2::jsonb, $3::jsonb, $4::faq_status, $5)
                RETURNING {FAQ_COLUMNS}
                """,
                payload.slug,
                json.dumps(payload.question.to_db()),
                json.dumps(payload.answer.to_db()),
                payload.status.value,
                payload.sort_order,
            ),
        )
    except asyncpg.UniqueViolationError as exc:
        raise DuplicateFAQSlugError from exc

    if row is None:
        raise RuntimeError("FAQ insert did not return a row")

    return _faq_from_record(row)


async def get_faq(pool: asyncpg.Pool, faq_id: UUID) -> FAQRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {FAQ_COLUMNS}
            FROM faqs
            WHERE id = $1
            """,
            faq_id,
        ),
    )
    if row is None:
        raise FAQNotFoundError

    return _faq_from_record(row)


async def list_faqs(
    pool: asyncpg.Pool,
    status_filter: FAQStatus | None,
    page: int,
    limit: int,
) -> FAQListResponse:
    params: list[object] = []
    where_clause = ""
    if status_filter is not None:
        params.append(status_filter.value)
        where_clause = "WHERE status = $1::faq_status"

    count_row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(f"SELECT count(*) AS total FROM faqs {where_clause}", *params),
    )
    total = cast(int, count_row["total"]) if count_row is not None else 0

    params.extend([limit, page_offset(page, limit)])
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {FAQ_COLUMNS}
            FROM faqs
            {where_clause}
            ORDER BY sort_order, slug, id
            LIMIT ${len(params) - 1}
            OFFSET ${len(params)}
            """,
            *params,
        ),
    )
    return FAQListResponse(
        items=[_faq_from_record(row) for row in rows],
        total=total,
        page=page,
        limit=limit,
        total_pages=page_count(total, limit),
    )


async def update_faq(pool: asyncpg.Pool, faq_id: UUID, payload: FAQUpdate) -> FAQRead:
    assignments: list[str] = []
    params: list[Any] = []

    if "slug" in payload.model_fields_set:
        params.append(payload.slug)
        assignments.append(f"slug = ${len(params)}")
    if "question" in payload.model_fields_set:
        question = cast(LocalizedQuestion, payload.question)
        params.append(json.dumps(question.to_db()))
        assignments.append(f"question = ${len(params)}::jsonb")
    if "answer" in payload.model_fields_set:
        answer = cast(LocalizedAnswer, payload.answer)
        params.append(json.dumps(answer.to_db()))
        assignments.append(f"answer = ${len(params)}::jsonb")
    if "status" in payload.model_fields_set:
        params.append(cast(FAQStatus, payload.status).value)
        assignments.append(f"status = ${len(params)}::faq_status")
    if "sort_order" in payload.model_fields_set:
        params.append(payload.sort_order)
        assignments.append(f"sort_order = ${len(params)}")

    params.append(faq_id)
    try:
        row = cast(
            Mapping[str, object] | None,
            await pool.fetchrow(
                f"""
                UPDATE faqs
                SET {", ".join(assignments)}
                WHERE id = ${len(params)}
                RETURNING {FAQ_COLUMNS}
                """,
                *params,
            ),
        )
    except asyncpg.UniqueViolationError as exc:
        raise DuplicateFAQSlugError from exc

    if row is None:
        raise FAQNotFoundError

    return _faq_from_record(row)


async def delete_faq(pool: asyncpg.Pool, faq_id: UUID) -> None:
    command_status = cast(str, await pool.execute("DELETE FROM faqs WHERE id = $1", faq_id))
    if _rows_affected(command_status) == 0:
        raise FAQNotFoundError


def _raise_faq_http_error(exc: FAQNotFoundError | DuplicateFAQSlugError) -> NoReturn:
    if isinstance(exc, FAQNotFoundError):
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="FAQ not found",
        ) from exc

    raise HTTPException(
        status_code=http_status.HTTP_409_CONFLICT,
        detail="FAQ slug already exists",
    ) from exc


@router.post("", response_model=FAQRead, status_code=http_status.HTTP_201_CREATED)
async def create_admin_faq(payload: FAQCreate, pool: DbPool) -> FAQRead:
    try:
        return await create_faq(pool, payload)
    except DuplicateFAQSlugError as exc:
        _raise_faq_http_error(exc)


@router.get("", response_model=FAQListResponse)
async def list_admin_faqs(
    pool: DbPool,
    status_filter: Annotated[FAQStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> FAQListResponse:
    return await list_faqs(pool, status_filter, page, limit)


@router.get("/{faq_id}", response_model=FAQRead)
async def read_admin_faq(faq_id: UUID, pool: DbPool) -> FAQRead:
    try:
        return await get_faq(pool, faq_id)
    except FAQNotFoundError as exc:
        _raise_faq_http_error(exc)


@router.patch("/{faq_id}", response_model=FAQRead)
async def update_admin_faq(faq_id: UUID, payload: FAQUpdate, pool: DbPool) -> FAQRead:
    try:
        return await update_faq(pool, faq_id, payload)
    except (FAQNotFoundError, DuplicateFAQSlugError) as exc:
        _raise_faq_http_error(exc)


@router.delete("/{faq_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_admin_faq(faq_id: UUID, pool: DbPool) -> Response:
    try:
        await delete_faq(pool, faq_id)
    except FAQNotFoundError as exc:
        _raise_faq_http_error(exc)

    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
