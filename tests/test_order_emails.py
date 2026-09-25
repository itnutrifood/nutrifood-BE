from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from typing import Any
from uuid import UUID

import pytest
from backend.apps.common.enums import LanguageCode, OrderStatus
from backend.apps.common.localization import resolve_email_language
from backend.apps.notifications.email_templates.order_confirmation import (
    render_order_confirmation,
    render_order_status_update,
)
from backend.apps.orders import tasks
from backend.apps.orders.exceptions import OrderNotFoundError
from backend.apps.orders.schemas import OrderRead
from backend.apps.products.schemas import LocalizedText
from backend.config.email import EmailService
from backend.config.settings import Settings
from fastapi import HTTPException

ORDER_ID = UUID("70000000-0000-0000-0000-000000000001")
ORDER_ITEM_ID = UUID("71000000-0000-0000-0000-000000000001")
IMAGE_URL = "https://cdn.example.test/products/bowl.jpg?size=64&v=1"
PUBLIC_PRODUCT_IMAGE_URL = (
    "https://dev-assets.nutrifood.am/products/images/c25bc5aa-2f3a-41ed-bcc6-b8caf6268384.jpg"
)


def sample_order() -> OrderRead:
    return OrderRead.model_validate(
        {
            "id": ORDER_ID,
            "order_number": "NFUX6Q8N6LD",
            "user_id": UUID("60000000-0000-0000-0000-000000000001"),
            "status": "pending",
            "payment_method": "cash_on_delivery",
            "payment_status": "unpaid",
            "subtotal": Decimal("25.98"),
            "delivery_fee": Decimal("2.00"),
            "total": Decimal("27.98"),
            "currency": "USD",
            "customer_first_name": "Jane",
            "customer_last_name": "Doe",
            "customer_email": "jane@example.com",
            "contact_phone": "+37499123456",
            "requested_delivery_at": datetime(2026, 9, 25, 10, 0, tzinfo=UTC),
            "created_at": datetime(2026, 9, 25, 8, 0, tzinfo=UTC),
            "updated_at": datetime(2026, 9, 25, 8, 0, tzinfo=UTC),
            "delivery_address": {
                "country": "Armenia",
                "region": "Yerevan",
                "city": "Yerevan",
                "street": "Northern Avenue",
                "building_number": "10/1",
                "entrance": "2",
                "floor": "5",
                "apartment": "17",
                "formatted_address": "Armenia, Yerevan, Northern Avenue, 10/1",
                "location": None,
                "location_source": "yandex",
            },
            "delivery_notes": "Call on arrival",
            "items": [
                {
                    "id": ORDER_ITEM_ID,
                    "product_id": UUID("72000000-0000-0000-0000-000000000001"),
                    "product_slug": "mediterranean-bowl",
                    "product_title": {
                        "EN-US": "Mediterranean Bowl",
                        "HY-AM": "Միջերկրածովյան բոուլ",
                        "RU-RU": "Средиземноморский боул",
                    },
                    "unit_price": Decimal("12.99"),
                    "quantity": 2,
                    "line_total": Decimal("25.98"),
                }
            ],
        }
    )


class EmailTaskPool:
    def __init__(self, image_url: str | None = IMAGE_URL) -> None:
        self.closed = False
        self.image_url = image_url
        self.image_query: str | None = None

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert args == (ORDER_ID,)
        self.image_query = query
        return [{"item_id": ORDER_ITEM_ID, "image_url": self.image_url}]

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_order_confirmation_email_contains_saved_order_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = EmailTaskPool()
    order = sample_order()
    sent: dict[str, Any] = {}

    async def create_task_pool() -> EmailTaskPool:
        return pool

    async def get_order(task_pool: object, order_id: UUID) -> OrderRead:
        assert task_pool is pool
        assert order_id == ORDER_ID
        return order

    async def fake_send_email(service: EmailService, **message: Any) -> int:
        sent.update(message)
        return 202

    monkeypatch.setattr(tasks, "create_pool", create_task_pool)
    monkeypatch.setattr(tasks.repository, "get_admin_order", get_order)
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: Settings(_env_file=None, sendgrid_api_key="sendgrid-api-key"),
    )
    monkeypatch.setattr(EmailService, "send_email", fake_send_email)

    assert await tasks._send_order_preparing_email(ORDER_ID) is True
    assert pool.closed is True
    assert sent["from_email"] == "info@nutrifood.am"
    assert sent["to_emails"] == "jane@example.com"
    assert sent["subject"] == "NutriFood order #NFUX6Q8N6LD received"
    assert pool.image_query is not None and "p.images -> 0 ->> 'url'" in pool.image_query
    assert (
        'src="https://cdn.example.test/products/bowl.jpg?size=64&amp;v=1"' in sent["html_content"]
    )
    assert 'alt="Mediterranean Bowl"' in sent["html_content"]
    assert IMAGE_URL not in sent["plain_text_content"]
    assert str(ORDER_ID) not in sent["plain_text_content"]
    assert str(ORDER_ID) not in sent["html_content"]
    for value in (
        "NFUX6Q8N6LD",
        "Mediterranean Bowl",
        "2 × 12.99 USD",
        "25.98 USD",
        "2.00 USD",
        "27.98 USD",
        "Northern Avenue",
        "+37499123456",
        "25 September 2026, 14:00 (Armenia time)",
        "Cash on delivery",
        "Call on arrival",
    ):
        assert value in sent["plain_text_content"]
        assert value in sent["html_content"]


def test_order_email_escapes_customer_and_catalog_content() -> None:
    order = sample_order()
    title = LocalizedText.model_validate(
        {"EN-US": "Bowl <script>", "HY-AM": "Բոուլ", "RU-RU": "Боул"}
    )
    order = order.model_copy(
        update={
            "customer_first_name": "Jane & Co",
            "delivery_notes": "Leave at <door>",
            "items": [order.items[0].model_copy(update={"product_title": title})],
        }
    )

    email = render_order_confirmation(order)

    assert "Jane &amp; Co" in email.html
    assert "Bowl &lt;script&gt;" in email.html
    assert "Leave at &lt;door&gt;" in email.html
    assert "Bowl <script>" in email.plain_text


@pytest.mark.parametrize(
    ("language", "tag", "heading", "title", "month", "subject"),
    [
        (
            LanguageCode.EN_US,
            "en",
            "Thanks for your order!",
            "Mediterranean Bowl",
            "September",
            "NutriFood order #NFUX6Q8N6LD received",
        ),
        (
            LanguageCode.HY_AM,
            "hy",
            "Շնորհակալություն պատվերի համար։",
            "Միջերկրածովյան բոուլ",
            "սեպտեմբերի",
            "Ձեր NutriFood #NFUX6Q8N6LD պատվերն ընդունվել է",
        ),
        (
            LanguageCode.RU_RU,
            "ru",
            "Спасибо за заказ!",
            "Средиземноморский боул",
            "сентября",
            "Заказ NutriFood №NFUX6Q8N6LD принят",
        ),
    ],
)
def test_order_email_uses_selected_language_for_all_content(
    language: LanguageCode,
    tag: str,
    heading: str,
    title: str,
    month: str,
    subject: str,
) -> None:
    email = render_order_confirmation(sample_order(), language, {ORDER_ITEM_ID: IMAGE_URL})

    assert f'<html lang="{tag}">' in email.html
    for value in (heading, title, month):
        assert value in email.html
        assert value in email.plain_text
    assert email.subject == subject
    assert f'alt="{title}"' in email.html
    assert str(ORDER_ID) not in email.html
    assert str(ORDER_ID) not in email.plain_text
    if language != LanguageCode.EN_US:
        assert "Mediterranean Bowl" not in email.html


@pytest.mark.parametrize(
    ("selected", "accepted", "expected"),
    [
        ("hy", "ru-RU, en;q=0.8", LanguageCode.HY_AM),
        ("ru-RU", None, LanguageCode.RU_RU),
        (None, "ru-RU, hy;q=0.8", LanguageCode.RU_RU),
        (None, "fr, hy;q=0.7, en;q=0.3", LanguageCode.HY_AM),
        (None, None, LanguageCode.EN_US),
    ],
)
def test_email_language_selection(
    selected: str | None,
    accepted: str | None,
    expected: LanguageCode,
) -> None:
    assert resolve_email_language(selected, accepted) == expected


def test_email_language_rejects_unsupported_explicit_locale() -> None:
    with pytest.raises(HTTPException) as exc_info:
        resolve_email_language("fr", None)

    assert exc_info.value.status_code == 422


def test_order_email_lists_all_items_and_omits_optional_delivery_details() -> None:
    order = sample_order()
    title = LocalizedText.model_validate(
        {"EN-US": "Green Salad", "HY-AM": "Աղցան", "RU-RU": "Салат"}
    )
    second_item = order.items[0].model_copy(
        update={
            "product_title": title,
            "quantity": 1,
            "unit_price": Decimal("8.50"),
            "line_total": Decimal("8.50"),
        }
    )
    order = order.model_copy(
        update={
            "items": [order.items[0], second_item],
            "subtotal": Decimal("34.48"),
            "total": Decimal("36.48"),
            "requested_delivery_at": None,
            "delivery_notes": None,
        }
    )

    email = render_order_confirmation(order)

    assert "Mediterranean Bowl" in email.html
    assert "Green Salad" in email.html
    assert "Green Salad" in email.plain_text
    assert "Requested delivery" not in email.html
    assert "Delivery notes" not in email.html


@pytest.mark.parametrize("image_url", ["javascript:alert(1)", "http://cdn.example.test/a.jpg"])
def test_order_email_omits_non_https_image_urls(image_url: str) -> None:
    email = render_order_confirmation(sample_order(), item_images={ORDER_ITEM_ID: image_url})

    assert "<img " not in email.html
    assert "Mediterranean Bowl" in email.html


def test_order_email_uses_public_product_image_url() -> None:
    email = render_order_confirmation(
        sample_order(), item_images={ORDER_ITEM_ID: PUBLIC_PRODUCT_IMAGE_URL}
    )

    assert f'src="{PUBLIC_PRODUCT_IMAGE_URL}"' in email.html


@pytest.mark.parametrize(
    ("language", "status", "heading"),
    [
        (LanguageCode.EN_US, OrderStatus.PREPARING, "We're preparing your order"),
        (LanguageCode.EN_US, OrderStatus.OUT_FOR_DELIVERY, "Your order is on its way"),
        (LanguageCode.EN_US, OrderStatus.DELIVERED, "Enjoy your order!"),
        (LanguageCode.HY_AM, OrderStatus.PREPARING, "Արդեն պատրաստում ենք Ձեր պատվերը"),
        (LanguageCode.HY_AM, OrderStatus.OUT_FOR_DELIVERY, "Ձեր պատվերը ճանապարհին է"),
        (LanguageCode.HY_AM, OrderStatus.DELIVERED, "Բարի ախորժակ։"),
        (LanguageCode.RU_RU, OrderStatus.PREPARING, "Мы уже готовим ваш заказ"),
        (LanguageCode.RU_RU, OrderStatus.OUT_FOR_DELIVERY, "Ваш заказ уже в пути"),
        (LanguageCode.RU_RU, OrderStatus.DELIVERED, "Приятного аппетита!"),
    ],
)
def test_status_email_keeps_order_details_in_each_language(
    language: LanguageCode, status: OrderStatus, heading: str
) -> None:
    order = sample_order().model_copy(update={"status": status})
    email = render_order_status_update(
        order, status, language, {ORDER_ITEM_ID: PUBLIC_PRODUCT_IMAGE_URL}
    )

    assert escape(heading) in email.html
    assert heading in email.plain_text
    assert "NFUX6Q8N6LD" in email.subject
    assert f'src="{PUBLIC_PRODUCT_IMAGE_URL}"' in email.html
    assert str(ORDER_ID) not in email.html
    assert str(ORDER_ID) not in email.plain_text
    for value in ("25.98 USD", "2.00 USD", "27.98 USD", "Northern Avenue", "+37499123456"):
        assert value in email.html
        assert value in email.plain_text
    assert "status has changed" not in email.plain_text


@pytest.mark.asyncio
async def test_status_email_uses_saved_order_language_and_skips_stale_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = EmailTaskPool(PUBLIC_PRODUCT_IMAGE_URL)
    order = sample_order().model_copy(
        update={"status": OrderStatus.OUT_FOR_DELIVERY, "email_language": LanguageCode.RU_RU}
    )
    sent: list[dict[str, Any]] = []

    async def create_task_pool() -> EmailTaskPool:
        return pool

    async def get_order(task_pool: object, order_id: UUID) -> OrderRead:
        assert task_pool is pool
        assert order_id == ORDER_ID
        return order

    async def fake_send_email(service: EmailService, **message: Any) -> int:
        sent.append(message)
        return 202

    monkeypatch.setattr(tasks, "create_pool", create_task_pool)
    monkeypatch.setattr(tasks.repository, "get_admin_order", get_order)
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: Settings(_env_file=None, sendgrid_api_key="sendgrid-api-key"),
    )
    monkeypatch.setattr(EmailService, "send_email", fake_send_email)

    assert await tasks._send_order_status_email(ORDER_ID, OrderStatus.PREPARING) is False
    assert sent == []
    assert await tasks._send_order_status_email(ORDER_ID, OrderStatus.OUT_FOR_DELIVERY) is True
    assert sent[0]["subject"] == "Ваш заказ NutriFood №NFUX6Q8N6LD уже в пути"
    assert "Средиземноморский боул" in sent[0]["html_content"]
    assert PUBLIC_PRODUCT_IMAGE_URL in sent[0]["html_content"]


@pytest.mark.asyncio
async def test_order_confirmation_email_skips_missing_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = EmailTaskPool()

    async def create_task_pool() -> EmailTaskPool:
        return pool

    async def get_order(task_pool: object, order_id: UUID) -> OrderRead:
        raise OrderNotFoundError

    async def unexpected_send_email(service: EmailService, **message: Any) -> int:
        raise AssertionError("Email must not be sent")

    monkeypatch.setattr(tasks, "create_pool", create_task_pool)
    monkeypatch.setattr(tasks.repository, "get_admin_order", get_order)
    monkeypatch.setattr(EmailService, "send_email", unexpected_send_email)

    assert await tasks._send_order_preparing_email(ORDER_ID) is False
    assert pool.closed is True
