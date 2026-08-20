from typing import Annotated, cast

from fastapi import Depends, Request
from redis.asyncio import Redis

from backend.config.settings import get_settings


def create_cache_client() -> Redis:
    settings = get_settings()
    return cast(
        Redis,
        Redis.from_url(settings.statistics_cache_url, decode_responses=True),
    )


def get_cache_client(request: Request) -> Redis:
    return cast(Redis, request.app.state.cache_client)


CacheClient = Annotated[Redis, Depends(get_cache_client)]
