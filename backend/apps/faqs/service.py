from dataclasses import dataclass
from uuid import UUID

import asyncpg

from backend.apps.common.enums import LanguageCode
from backend.apps.common.exceptions import InvalidCursorError
from backend.apps.common.localization import required_localized_text
from backend.apps.common.pagination import (
    CursorPage,
    decode_cursor,
    encode_cursor,
)
from backend.apps.faqs import repository
from backend.apps.faqs.exceptions import FAQNotFoundError
from backend.apps.faqs.schemas import FAQRead, PublicFAQRead

PublicFAQNotFoundError = FAQNotFoundError


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
    parsed_cursor: FAQCursor | None = None
    if cursor is not None:
        parsed_cursor = _parse_faq_cursor(cursor)

    faqs = await repository.list_active_faqs(
        pool,
        limit,
        (parsed_cursor.sort_order, parsed_cursor.slug, parsed_cursor.id)
        if parsed_cursor is not None
        else None,
    )
    next_cursor = _faq_cursor(faqs[limit - 1]) if len(faqs) > limit else None
    return CursorPage(
        items=[_public_faq(faq, language) for faq in faqs[:limit]],
        limit=limit,
        next_cursor=next_cursor,
    )


async def get_public_faq(
    pool: asyncpg.Pool,
    language: LanguageCode,
    faq_id: UUID,
) -> PublicFAQRead:
    faq = await repository.get_active_faq(pool, faq_id)
    return _public_faq(faq, language)


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
