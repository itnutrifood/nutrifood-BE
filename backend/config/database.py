from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, TypedDict, cast

import asyncpg
from fastapi import Depends, FastAPI, Request
from redis.asyncio import Redis

from backend.apps.users.addresses.geocoding import YandexGeocoder, create_yandex_geocoder
from backend.config.cache import create_cache_client
from backend.config.firebase import FirebaseService, create_firebase_service
from backend.config.settings import get_settings


class AppState(TypedDict):
    db_pool: asyncpg.Pool
    cache_client: Redis
    firebase_service: FirebaseService
    address_geocoder: YandexGeocoder


async def create_pool() -> asyncpg.Pool:
    settings = get_settings()
    return await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=10)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = await create_pool()
    cache_client = create_cache_client()
    address_geocoder = create_yandex_geocoder()
    firebase_service: FirebaseService | None = None
    try:
        firebase_service = create_firebase_service()
        app.state.db_pool = pool
        app.state.cache_client = cache_client
        app.state.firebase_service = firebase_service
        app.state.address_geocoder = address_geocoder
        yield
    finally:
        try:
            if firebase_service is not None:
                firebase_service.close()
        finally:
            try:
                await address_geocoder.close()
            finally:
                try:
                    await cache_client.aclose()
                finally:
                    await pool.close()


def get_pool(request: Request) -> asyncpg.Pool:
    return cast(asyncpg.Pool, request.app.state.db_pool)


DbPool = Annotated[asyncpg.Pool, Depends(get_pool)]
