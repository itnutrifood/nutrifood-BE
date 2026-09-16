from typing import Any
from uuid import UUID

import pytest
from backend.apps.orders import tasks
from backend.config.email import EmailService
from backend.config.settings import Settings

ORDER_ID = UUID("70000000-0000-0000-0000-000000000001")


class EmailTaskPool:
    def __init__(self, recipient: str | None) -> None:
        self.recipient = recipient
        self.closed = False
        self.query: str | None = None
        self.args: tuple[object, ...] | None = None

    async def fetchrow(self, query: str, *args: object) -> dict[str, str] | None:
        self.query = query
        self.args = args
        if self.recipient is None:
            return None
        return {"customer_email": self.recipient}

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_order_preparing_email_is_sent_to_opted_in_customer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = EmailTaskPool("jane@example.com")
    sent: dict[str, Any] = {}

    async def create_task_pool() -> EmailTaskPool:
        return pool

    async def fake_send_email(service: EmailService, **message: Any) -> int:
        sent.update(message)
        return 202

    monkeypatch.setattr(tasks, "create_pool", create_task_pool)
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            sendgrid_api_key="sendgrid-api-key",
        ),
    )
    monkeypatch.setattr(EmailService, "send_email", fake_send_email)

    delivered = await tasks._send_order_preparing_email(ORDER_ID)

    assert delivered is True
    assert pool.closed is True
    assert pool.args == (ORDER_ID,)
    assert pool.query is not None and "np.order_confirmations" in pool.query
    assert sent == {
        "from_email": "info@nutrifood.am",
        "to_emails": "jane@example.com",
        "subject": tasks.ORDER_PREPARING_EMAIL_SUBJECT,
        "plain_text_content": "Your order is being prepared for delivery.",
    }


@pytest.mark.asyncio
async def test_order_preparing_email_is_skipped_when_customer_opted_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = EmailTaskPool(None)

    async def create_task_pool() -> EmailTaskPool:
        return pool

    async def unexpected_send_email(service: EmailService, **message: Any) -> int:
        raise AssertionError("Email must not be sent")

    monkeypatch.setattr(tasks, "create_pool", create_task_pool)
    monkeypatch.setattr(EmailService, "send_email", unexpected_send_email)

    delivered = await tasks._send_order_preparing_email(ORDER_ID)

    assert delivered is False
    assert pool.closed is True
