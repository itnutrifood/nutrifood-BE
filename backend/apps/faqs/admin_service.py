from uuid import UUID

import asyncpg

from backend.apps.common.enums import FAQStatus
from backend.apps.faqs import repository
from backend.apps.faqs.schemas import FAQCreate, FAQListResponse, FAQRead, FAQUpdate


async def create_faq(pool: asyncpg.Pool, payload: FAQCreate) -> FAQRead:
    return await repository.create_faq(pool, payload)


async def get_faq(pool: asyncpg.Pool, faq_id: UUID) -> FAQRead:
    return await repository.get_faq(pool, faq_id)


async def list_faqs(
    pool: asyncpg.Pool,
    status_filter: FAQStatus | None,
    page: int,
    limit: int,
) -> FAQListResponse:
    return await repository.list_faqs(pool, status_filter, page, limit)


async def update_faq(pool: asyncpg.Pool, faq_id: UUID, payload: FAQUpdate) -> FAQRead:
    return await repository.update_faq(pool, faq_id, payload)


async def delete_faq(pool: asyncpg.Pool, faq_id: UUID) -> None:
    await repository.delete_faq(pool, faq_id)
