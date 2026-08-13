import asyncio

import asyncpg
from celery.utils.log import get_task_logger

from backend.apps.notifications.service import prune_stale_fcm_registrations as prune_service
from backend.config.celery_app import app
from backend.config.database import create_pool
from backend.config.settings import get_settings

logger = get_task_logger(__name__)


async def _prune_stale_fcm_registrations() -> int:
    settings = get_settings()
    pool = await create_pool()
    try:
        return await prune_service(
            pool,
            stale_days=settings.fcm_registration_stale_days,
        )
    finally:
        await pool.close()


@app.task(  # type: ignore[untyped-decorator]
    name="backend.apps.notifications.tasks.prune_stale_fcm_registrations",
    autoretry_for=(asyncpg.PostgresError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
    ignore_result=True,
)
def prune_stale_fcm_registrations() -> int:
    removed_count = asyncio.run(_prune_stale_fcm_registrations())
    logger.info("Pruned %d stale FCM registrations", removed_count)
    return removed_count
