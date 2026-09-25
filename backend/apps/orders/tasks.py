import asyncio
import logging
from uuid import UUID

from backend.apps.common.enums import LanguageCode, OrderStatus
from backend.apps.notifications.email_templates.order_confirmation import (
    OrderEmail,
    render_order_confirmation,
    render_order_status_update,
)
from backend.apps.orders import repository
from backend.apps.orders.exceptions import OrderNotFoundError
from backend.apps.orders.schemas import OrderRead
from backend.config.celery_app import app
from backend.config.database import create_pool
from backend.config.email import EmailFromAddress, EmailService
from backend.config.settings import get_settings

logger = logging.getLogger(__name__)


async def _load_order_email_data(order_id: UUID) -> tuple[OrderRead, dict[UUID, str]] | None:
    pool = await create_pool()
    try:
        try:
            order = await repository.get_admin_order(pool, order_id)
        except OrderNotFoundError:
            return None
        try:
            item_images = await repository.get_order_item_image_urls(pool, order_id)
        except Exception:
            logger.exception("Could not load order item images order_id=%s", order_id)
            item_images = {}
    finally:
        await pool.close()
    return order, item_images


async def _send_order_email(order_id: UUID, email: OrderEmail, kind: str, address: str) -> bool:
    settings = get_settings()
    if not settings.sendgrid_api_key.strip():
        logger.warning(
            "Skipped %s email because SendGrid API key is not configured order_id=%s",
            kind,
            order_id,
        )
        return False

    service = EmailService(settings.sendgrid_api_key)
    status_code = await service.send_email(
        from_email=EmailFromAddress.INFO,
        to_emails=address,
        subject=email.subject,
        plain_text_content=email.plain_text,
        html_content=email.html,
    )
    logger.info(
        "Sent %s email order_id=%s status_code=%d",
        kind,
        order_id,
        status_code,
    )
    return True


async def _send_order_preparing_email(
    order_id: UUID,
    language: LanguageCode = LanguageCode.EN_US,
) -> bool:
    data = await _load_order_email_data(order_id)
    if data is None:
        return False
    order, item_images = data
    email = render_order_confirmation(order, language, item_images)
    return await _send_order_email(order_id, email, "order confirmation", order.customer_email)


async def _send_order_status_email(order_id: UUID, status: OrderStatus) -> bool:
    data = await _load_order_email_data(order_id)
    if data is None:
        return False
    order, item_images = data
    if order.status != status:
        logger.info("Skipped stale order status email order_id=%s status=%s", order_id, status)
        return False
    email = render_order_status_update(order, status, order.email_language, item_images)
    return await _send_order_email(order_id, email, "order status", order.customer_email)


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


@app.task(  # type: ignore[untyped-decorator]
    name="backend.apps.orders.tasks.send_order_status_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
    ignore_result=True,
)
def send_order_status_email(order_id: str, status: str) -> bool:
    return asyncio.run(_send_order_status_email(UUID(order_id), OrderStatus(status)))
