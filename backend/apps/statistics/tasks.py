import asyncio

import asyncpg
from celery.utils.log import get_task_logger
from redis.exceptions import RedisError

from backend.apps.statistics.schemas import PublicStatistics
from backend.apps.statistics.service import refresh_statistics_cache as refresh_service
from backend.config.cache import create_cache_client
from backend.config.celery_app import app
from backend.config.database import create_pool

logger = get_task_logger(__name__)


async def _refresh_statistics_cache() -> PublicStatistics:
    pool = await create_pool()
    cache = create_cache_client()
    try:
        return await refresh_service(pool, cache)
    finally:
        try:
            await cache.aclose()
        finally:
            await pool.close()


@app.task(  # type: ignore[untyped-decorator]
    name="backend.apps.statistics.tasks.refresh_statistics_cache",
    autoretry_for=(asyncpg.PostgresError, RedisError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
    ignore_result=True,
)
def refresh_statistics_cache() -> dict[str, int | float]:
    statistics = asyncio.run(_refresh_statistics_cache())
    logger.info("Refreshed public statistics cache")
    return statistics.model_dump()
