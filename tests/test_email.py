from typing import Any

import pytest
from backend.config.email import (
    EmailService,
    EmailServiceNotConfiguredError,
    _create_email_service,
    get_email_service,
)
from backend.config.settings import Settings


class FakeResponse:
    status_code = 202


class FakeSendGridClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.message: Any = None

    def send(self, message: Any) -> FakeResponse:
        self.message = message
        return FakeResponse()


@pytest.mark.asyncio
async def test_send_email_builds_and_sends_message(monkeypatch: pytest.MonkeyPatch) -> None:
    clients: list[FakeSendGridClient] = []

    def create_client(*, api_key: str) -> FakeSendGridClient:
        client = FakeSendGridClient(api_key)
        clients.append(client)
        return client

    monkeypatch.setattr("backend.config.email.SendGridAPIClient", create_client)
    service = EmailService(" secret-key ")

    status_code = await service.send_email(
        from_email="orders@nutrifood.example",
        to_emails=["customer@example.com", "copy@example.com"],
        subject="Order confirmed",
        plain_text_content="Your order is confirmed.",
        html_content="<p>Your order is confirmed.</p>",
    )

    assert status_code == 202
    assert clients[0].api_key == "secret-key"
    assert clients[0].message.get() == {
        "from": {"email": "orders@nutrifood.example"},
        "subject": "Order confirmed",
        "personalizations": [
            {
                "to": [
                    {"email": "customer@example.com"},
                    {"email": "copy@example.com"},
                ]
            }
        ],
        "content": [
            {"type": "text/plain", "value": "Your order is confirmed."},
            {"type": "text/html", "value": "<p>Your order is confirmed.</p>"},
        ],
    }


def test_email_service_requires_api_key() -> None:
    with pytest.raises(EmailServiceNotConfiguredError, match="SENDGRID_API_KEY"):
        EmailService("  ")


@pytest.mark.asyncio
async def test_send_email_requires_content() -> None:
    service = EmailService("secret-key")

    with pytest.raises(ValueError, match="content variant"):
        await service.send_email(
            from_email="orders@nutrifood.example",
            to_emails="customer@example.com",
            subject="Order confirmed",
        )


def test_get_email_service_uses_configured_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _create_email_service.cache_clear()
    clients: list[FakeSendGridClient] = []

    def create_client(*, api_key: str) -> FakeSendGridClient:
        client = FakeSendGridClient(api_key)
        clients.append(client)
        return client

    monkeypatch.setattr("backend.config.email.SendGridAPIClient", create_client)
    settings = Settings(_env_file=None, sendgrid_api_key="configured-key")

    service = get_email_service(settings)

    assert isinstance(service, EmailService)
    assert clients[0].api_key == "configured-key"
    _create_email_service.cache_clear()
