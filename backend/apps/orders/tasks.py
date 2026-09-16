import asyncio
import logging
from uuid import UUID

from backend.apps.orders import repository
from backend.config.celery_app import app
from backend.config.database import create_pool
from backend.config.email import EmailFromAddress, EmailService
from backend.config.settings import get_settings

logger = logging.getLogger(__name__)

ORDER_PREPARING_EMAIL_SUBJECT = "Your NutriFood order is being prepared"
ORDER_PREPARING_EMAIL_BODY = "Your order is being prepared for delivery."


async def _send_order_preparing_email(order_id: UUID) -> bool:
    pool = await create_pool()
    try:
        recipient = await repository.get_order_confirmation_recipient(pool, order_id)
    finally:
        await pool.close()

    if recipient is None:
        return False

    settings = get_settings()
    if not settings.sendgrid_api_key.strip():
        logger.warning(
            "Skipped order preparation email because SendGrid API key is not configured "
            "order_id=%s",
            order_id,
        )
        return False

    service = EmailService(settings.sendgrid_api_key)
    status_code = await service.send_email(
        from_email=EmailFromAddress.INFO,
        to_emails=recipient,
        subject=ORDER_PREPARING_EMAIL_SUBJECT,
        plain_text_content=ORDER_PREPARING_EMAIL_BODY,
    )
    logger.info(
        "Sent order preparation email order_id=%s status_code=%d",
        order_id,
        status_code,
    )
    return True


@app.task(  # type: ignore[untyped-decorator]
    name="backend.apps.orders.tasks.send_order_preparing_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
    ignore_result=True,
)
def send_order_preparing_email(order_id: str) -> bool:
    return asyncio.run(_send_order_preparing_email(UUID(order_id)))
