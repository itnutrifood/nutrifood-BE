import hashlib
import logging
from collections.abc import Awaitable
from typing import cast

from fastapi import HTTPException, status
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

ADMIN_LOGIN_RATE_LIMIT_WINDOW_SECONDS = 15 * 60
ADMIN_LOGIN_IDENTIFIER_LIMIT = 5
ADMIN_LOGIN_SOURCE_LIMIT = 30
ADMIN_LOGIN_RATE_LIMIT_PREFIX = "nutrifood:admin-auth:login"

_INCREMENT_LOGIN_LIMITS_SCRIPT = """
local identifier_count = redis.call('INCR', KEYS[1])
if identifier_count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end

local source_count = redis.call('INCR', KEYS[2])
if source_count == 1 then
    redis.call('EXPIRE', KEYS[2], ARGV[1])
end

return {identifier_count, source_count}
"""


def _rate_limit_key(kind: str, value: str) -> str:
    digest = hashlib.sha256(value.strip().casefold().encode("utf-8")).hexdigest()
    return f"{ADMIN_LOGIN_RATE_LIMIT_PREFIX}:{kind}:{digest}"


async def enforce_admin_login_rate_limit(
    cache: Redis,
    identifier: str,
    source: str,
) -> None:
    identifier_key = _rate_limit_key("identifier", identifier)
    source_key = _rate_limit_key("source", source)

    try:
        raw_counts = await cast(
            Awaitable[object],
            cache.eval(
                _INCREMENT_LOGIN_LIMITS_SCRIPT,
                2,
                identifier_key,
                source_key,
                str(ADMIN_LOGIN_RATE_LIMIT_WINDOW_SECONDS),
            ),
        )
        counts = cast(list[object], raw_counts)
        identifier_count = int(cast(int | bytes | str, counts[0]))
        source_count = int(cast(int | bytes | str, counts[1]))
    except (IndexError, RedisError, TypeError, ValueError):
        logger.error("Admin login rate limiter is unavailable", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin authentication is temporarily unavailable",
        ) from None

    if (
        identifier_count > ADMIN_LOGIN_IDENTIFIER_LIMIT
        or source_count > ADMIN_LOGIN_SOURCE_LIMIT
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many admin login attempts",
            headers={"Retry-After": str(ADMIN_LOGIN_RATE_LIMIT_WINDOW_SECONDS)},
        )
