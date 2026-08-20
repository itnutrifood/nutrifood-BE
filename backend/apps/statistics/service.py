import logging
from typing import cast

import asyncpg
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from backend.apps.statistics import repository
from backend.apps.statistics.schemas import PublicStatistics

logger = logging.getLogger(__name__)

HAPPY_CUSTOMERS_CACHE_KEY = "nutrifood:statistics:happy_customers"
HEALTY_MEALS_CACHE_KEY = "nutrifood:statistics:healty_meals"
CUSTOMER_RATING_CACHE_KEY = "nutrifood:statistics:customer_rating"
STATISTICS_CACHE_KEYS = (
    HAPPY_CUSTOMERS_CACHE_KEY,
    HEALTY_MEALS_CACHE_KEY,
    CUSTOMER_RATING_CACHE_KEY,
)


def _cache_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, str):
        return value
    raise ValueError("Unexpected statistics cache value")


async def read_cached_statistics(cache: Redis) -> PublicStatistics | None:
    values = cast(list[object | None], await cache.mget(list(STATISTICS_CACHE_KEYS)))
    if len(values) != len(STATISTICS_CACHE_KEYS) or any(value is None for value in values):
        return None

    try:
        return PublicStatistics(
            happy_customers=int(_cache_text(values[0])),
            healty_meals=int(_cache_text(values[1])),
            customer_rating=float(_cache_text(values[2])),
        )
    except (UnicodeDecodeError, ValueError, ValidationError):
        return None


async def cache_statistics(cache: Redis, statistics: PublicStatistics) -> None:
    await cache.mset(
        {
            HAPPY_CUSTOMERS_CACHE_KEY: str(statistics.happy_customers),
            HEALTY_MEALS_CACHE_KEY: str(statistics.healty_meals),
            CUSTOMER_RATING_CACHE_KEY: str(statistics.customer_rating),
        }
    )


async def refresh_statistics_cache(
    pool: asyncpg.Pool,
    cache: Redis,
) -> PublicStatistics:
    statistics = await repository.get_public_statistics(pool)
    await cache_statistics(cache, statistics)
    return statistics


async def get_public_statistics(
    pool: asyncpg.Pool,
    cache: Redis,
) -> PublicStatistics:
    try:
        cached_statistics = await read_cached_statistics(cache)
    except RedisError:
        logger.warning("Could not read public statistics from Redis", exc_info=True)
    else:
        if cached_statistics is not None:
            return cached_statistics

    statistics = await repository.get_public_statistics(pool)
    try:
        await cache_statistics(cache, statistics)
    except RedisError:
        logger.warning("Could not write public statistics to Redis", exc_info=True)
    return statistics
