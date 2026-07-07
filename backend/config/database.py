from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TypedDict, cast

import asyncpg
from fastapi import FastAPI, Request

from backend.config.settings import get_settings


class AppState(TypedDict):
    db_pool: asyncpg.Pool


async def create_pool() -> asyncpg.Pool:
    settings = get_settings()
    return await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=10)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = await create_pool()
    app.state.db_pool = pool
    try:
        yield
    finally:
        await pool.close()


def get_pool(request: Request) -> asyncpg.Pool:
    return cast(asyncpg.Pool, request.app.state.db_pool)
