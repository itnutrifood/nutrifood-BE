from typing import Annotated, NoReturn
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from backend.apps.common.localization import LocaleFromPath
from backend.apps.common.pagination import CursorPage, InvalidCursorError
from backend.apps.faqs.schemas import PublicFAQRead
from backend.apps.faqs.service import PublicFAQNotFoundError, get_public_faq
from backend.apps.faqs.service import list_public_faqs as list_public_faqs_service
from backend.config.database import get_pool

DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]

router = APIRouter(prefix="/faqs", tags=["faqs"])


def _raise_faq_http_error(exc: InvalidCursorError | PublicFAQNotFoundError) -> NoReturn:
    if isinstance(exc, InvalidCursorError):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid cursor",
        ) from exc

    raise HTTPException(
        status_code=http_status.HTTP_404_NOT_FOUND,
        detail="FAQ not found",
    ) from exc


@router.get("", response_model=CursorPage[PublicFAQRead])
async def list_public_faqs(
    language: LocaleFromPath,
    pool: DbPool,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> CursorPage[PublicFAQRead]:
    try:
        return await list_public_faqs_service(pool, language, limit, cursor)
    except InvalidCursorError as exc:
        _raise_faq_http_error(exc)


@router.get("/{faq_id}", response_model=PublicFAQRead)
async def read_public_faq(
    language: LocaleFromPath,
    faq_id: UUID,
    pool: DbPool,
) -> PublicFAQRead:
    try:
        return await get_public_faq(pool, language, faq_id)
    except PublicFAQNotFoundError as exc:
        _raise_faq_http_error(exc)
