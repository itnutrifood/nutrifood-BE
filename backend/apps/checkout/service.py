import hashlib
import json
import logging
from uuid import UUID

import asyncpg

from backend.apps.checkout import repository
from backend.apps.orders.schemas import OrderRead, PlaceOrderRequest
from backend.apps.orders.tasks import send_order_preparing_email

logger = logging.getLogger(__name__)


def request_fingerprint(payload: PlaceOrderRequest) -> str:
    canonical_payload = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


async def place_order(
    pool: asyncpg.Pool,
    user_id: UUID,
    payload: PlaceOrderRequest,
    idempotency_key: str,
    currency: str,
) -> OrderRead:
    result = await repository.place_order(
        pool,
        user_id,
        payload,
        idempotency_key,
        request_fingerprint(payload),
        currency,
    )
    if result.created:
        try:
            send_order_preparing_email.delay(str(result.order.id))
        except Exception:
            logger.exception(
                "Could not enqueue order preparation email order_id=%s",
                result.order.id,
            )
    return result.order
