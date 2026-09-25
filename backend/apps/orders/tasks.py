import asyncio
import logging
from uuid import UUID

from backend.apps.common.enums import LanguageCode
from backend.apps.notifications.email_templates.order_confirmation import render_order_confirmation
from backend.apps.orders import repository
from backend.apps.orders.exceptions import OrderNotFoundError
from backend.config.celery_app import app
from backend.config.database import create_pool
from backend.config.email import EmailFromAddress, EmailService
from backend.config.settings import get_settings

logger = logging.getLogger(__name__)


async def _send_order_preparing_email(
    order_id: UUID,
    language: LanguageCode = LanguageCode.EN_US,
) -> bool:
    pool = await create_pool()
    try:
        try:
            order = await repository.get_admin_order(pool, order_id)
        except OrderNotFoundError:
            return False
        try:
            item_images = await repository.get_order_item_image_urls(pool, order_id)
        except Exception:
            logger.exception("Could not load order item images order_id=%s", order_id)
            item_images = {}
    finally:
        await pool.close()

    settings = get_settings()
    if not settings.sendgrid_api_key.strip():
        logger.warning(
            "Skipped order confirmation email because SendGrid API key is not configured "
            "order_id=%s",
            order_id,
        )
        return False

    service = EmailService(settings.sendgrid_api_key)
    email = render_order_confirmation(order, language, item_images)
    status_code = await service.send_email(
        from_email=EmailFromAddress.INFO,
        to_emails=order.customer_email,
        subject=email.subject,
        plain_text_content=email.plain_text,
        html_content=email.html,
    )
    logger.info(
        "Sent order confirmation email order_id=%s status_code=%d",
        order_id,
        status_code,
    )
    return True


# Keep the registered name for order emails already waiting in the queue.
@app.task(  # type: ignore[untyped-decorator]
    name="backend.apps.orders.tasks.send_order_preparing_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
    ignore_result=True,
)
def send_order_preparing_email(order_id: str, language: str = LanguageCode.EN_US.value) -> bool:
    return asyncio.run(_send_order_preparing_email(UUID(order_id), LanguageCode(language)))
