from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast
from uuid import UUID

import asyncpg

from backend.apps.admin.faqs import FAQ_COLUMNS, FAQRead, _faq_from_record
from backend.apps.common.enums import FAQStatus, LanguageCode
from backend.apps.common.localization import required_localized_text
from backend.apps.common.pagination import (
    CursorPage,
    InvalidCursorError,
    decode_cursor,
    encode_cursor,
)
from backend.apps.faqs.schemas import PublicFAQRead


class PublicFAQNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class FAQCursor:
    sort_order: int
    slug: str
    id: UUID


def _parse_faq_cursor(cursor: str) -> FAQCursor:
    payload = decode_cursor(cursor)
    sort_order = payload.get("sort_order")
    slug = payload.get("slug")
    faq_id = payload.get("id")

    if isinstance(sort_order, bool) or not isinstance(sort_order, int):
        raise InvalidCursorError("Invalid FAQ cursor")
    if not isinstance(slug, str) or not slug:
        raise InvalidCursorError("Invalid FAQ cursor")
    if not isinstance(faq_id, str):
        raise InvalidCursorError("Invalid FAQ cursor")

    try:
        parsed_faq_id = UUID(faq_id)
    except ValueError as exc:
        raise InvalidCursorError("Invalid FAQ cursor") from exc

    return FAQCursor(sort_order=sort_order, slug=slug, id=parsed_faq_id)


def _faq_cursor(faq: FAQRead) -> str:
    return encode_cursor({"sort_order": faq.sort_order, "slug": faq.slug, "id": faq.id})


async def list_public_faqs(
    pool: asyncpg.Pool,
    language: LanguageCode,
    limit: int,
    cursor: str | None,
) -> CursorPage[PublicFAQRead]:
    params: list[object] = [FAQStatus.ACTIVE.value]
    conditions = ["status = $1::faq_status"]

    if cursor is not None:
        faq_cursor = _parse_faq_cursor(cursor)
        params.extend([faq_cursor.sort_order, faq_cursor.slug, faq_cursor.id])
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
    faqs = [_faq_from_record(row) for row in rows[:limit]]
    next_cursor = _faq_cursor(faqs[-1]) if len(rows) > limit else None
    return CursorPage(
        items=[_public_faq(faq, language) for faq in faqs],
        limit=limit,
        next_cursor=next_cursor,
    )


async def get_public_faq(
    pool: asyncpg.Pool,
    language: LanguageCode,
    faq_id: UUID,
) -> PublicFAQRead:
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
        raise PublicFAQNotFoundError

    return _public_faq(_faq_from_record(row), language)


def _public_faq(faq: FAQRead, language: LanguageCode) -> PublicFAQRead:
    return PublicFAQRead(
        id=faq.id,
        slug=faq.slug,
        question=required_localized_text(faq.question.to_db(), language),
        answer=required_localized_text(faq.answer.to_db(), language),
        sort_order=faq.sort_order,
        created_at=faq.created_at,
        updated_at=faq.updated_at,
    )
