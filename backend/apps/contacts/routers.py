from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends
from fastapi import status as http_status

from backend.apps.contacts.schemas import ContactMessageCreate, ContactMessageRead
from backend.apps.contacts.service import create_contact_message
from backend.config.database import get_pool

DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]

router = APIRouter(prefix="/contact-us", tags=["contact-us"])


@router.post("", response_model=ContactMessageRead, status_code=http_status.HTTP_201_CREATED)
async def submit_contact_message(
    payload: ContactMessageCreate,
    pool: DbPool,
) -> ContactMessageRead:
    return await create_contact_message(pool, payload)
