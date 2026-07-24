import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import asyncpg

from backend.apps.common.db import json_object, rows_affected
from backend.apps.common.enums import FAQStatus
from backend.apps.common.pagination import page_count, page_offset
from backend.apps.faqs.exceptions import DuplicateFAQSlugError, FAQNotFoundError
from backend.apps.faqs.schemas import (
    FAQCreate,
    FAQListResponse,
    FAQRead,
    FAQUpdate,
    LocalizedAnswer,
    LocalizedQuestion,
)

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


def faq_from_record(record: Mapping[str, object]) -> FAQRead:
    return FAQRead(
        id=cast(UUID, record["id"]),
        slug=cast(str, record["slug"]),
        question=LocalizedQuestion.model_validate(json_object(record["question"])),
        answer=LocalizedAnswer.model_validate(json_object(record["answer"])),
        status=FAQStatus(cast(str, record["status"])),
        sort_order=cast(int, record["sort_order"]),
        created_at=cast(datetime, record["created_at"]),
        updated_at=cast(datetime, record["updated_at"]),
    )


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

    return faq_from_record(row)


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

    return faq_from_record(row)


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
        items=[faq_from_record(row) for row in rows],
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

    return faq_from_record(row)


async def delete_faq(pool: asyncpg.Pool, faq_id: UUID) -> None:
    command_status = cast(str, await pool.execute("DELETE FROM faqs WHERE id = $1", faq_id))
    if rows_affected(command_status) == 0:
        raise FAQNotFoundError


async def list_active_faqs(
    pool: asyncpg.Pool,
    limit: int,
    cursor: tuple[int, str, UUID] | None,
) -> list[FAQRead]:
    params: list[object] = [FAQStatus.ACTIVE.value]
    conditions = ["status = $1::faq_status"]

    if cursor is not None:
        params.extend(cursor)
        conditions.append(
            f"(sort_order, slug, id) > (${len(params) - 2}, ${len(params) - 1}, ${len(params)})"
        )

    params.append(limit + 1)
    rows = cast(
        Sequence[Mapping[str, object]],
        await pool.fetch(
            f"""
            SELECT {FAQ_COLUMNS}
            FROM faqs
            WHERE {" AND ".join(conditions)}
            ORDER BY sort_order, slug, id
            LIMIT ${len(params)}
            """,
            *params,
        ),
    )
    return [faq_from_record(row) for row in rows]


async def get_active_faq(pool: asyncpg.Pool, faq_id: UUID) -> FAQRead:
    row = cast(
        Mapping[str, object] | None,
        await pool.fetchrow(
            f"""
            SELECT {FAQ_COLUMNS}
            FROM faqs
            WHERE id = $1
                AND status = $2::faq_status
            """,
            faq_id,
            FAQStatus.ACTIVE.value,
        ),
    )
    if row is None:
        raise FAQNotFoundError

    return faq_from_record(row)
