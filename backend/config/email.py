from collections.abc import Sequence
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from starlette.concurrency import run_in_threadpool

from backend.config.settings import Settings, get_settings


class EmailServiceNotConfiguredError(RuntimeError):
    """Raised when email delivery is used without a SendGrid API key."""


class EmailService:
    """Async facade over the synchronous SendGrid client."""

    def __init__(self, api_key: str) -> None:
        normalized_api_key = api_key.strip()
        if not normalized_api_key:
            raise EmailServiceNotConfiguredError("SENDGRID_API_KEY is not configured")
        self._client: Any = SendGridAPIClient(api_key=normalized_api_key)

    async def send_email(
        self,
        *,
        from_email: str,
        to_emails: str | Sequence[str],
        subject: str,
        plain_text_content: str | None = None,
        html_content: str | None = None,
    ) -> int:
        """Send an email and return SendGrid's HTTP response status code."""
        if plain_text_content is None and html_content is None:
            raise ValueError("At least one email content variant is required")

        recipients: str | list[str]
        if isinstance(to_emails, str):
            recipients = to_emails
        else:
            recipients = list(to_emails)
            if not recipients:
                raise ValueError("At least one recipient is required")

        message = Mail(
            from_email=from_email,
            to_emails=recipients,
            subject=subject,
            plain_text_content=plain_text_content,
            html_content=html_content,
        )
        response = await run_in_threadpool(self._client.send, message)
        return int(response.status_code)


@lru_cache
def _create_email_service(api_key: str) -> EmailService:
    return EmailService(api_key)


def get_email_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmailService:
    return _create_email_service(settings.sendgrid_api_key)


EmailServiceDependency = Annotated[
    EmailService,
    Depends(get_email_service),
]
