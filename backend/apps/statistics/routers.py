from fastapi import APIRouter

from backend.apps.statistics.schemas import PublicStatistics
from backend.apps.statistics.service import get_public_statistics as get_statistics_service
from backend.config.cache import CacheClient
from backend.config.database import DbPool

router = APIRouter(prefix="/statistics", tags=["statistics"])


@router.get("", response_model=PublicStatistics)
async def read_public_statistics(
    pool: DbPool,
    cache: CacheClient,
) -> PublicStatistics:
    return await get_statistics_service(pool, cache)
