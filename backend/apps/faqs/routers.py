from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from backend.apps.common.localization import LocaleFromPath
from backend.apps.common.pagination import CursorPage
from backend.apps.faqs.schemas import PublicFAQRead
from backend.apps.faqs.service import get_public_faq
from backend.apps.faqs.service import list_public_faqs as list_public_faqs_service
from backend.config.database import DbPool

router = APIRouter(prefix="/faqs", tags=["faqs"])


@router.get("", response_model=CursorPage[PublicFAQRead])
async def list_public_faqs(
    language: LocaleFromPath,
    pool: DbPool,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> CursorPage[PublicFAQRead]:
    return await list_public_faqs_service(pool, language, limit, cursor)


@router.get("/{faq_id}", response_model=PublicFAQRead)
async def read_public_faq(
    language: LocaleFromPath,
    faq_id: UUID,
    pool: DbPool,
) -> PublicFAQRead:
    return await get_public_faq(pool, language, faq_id)
