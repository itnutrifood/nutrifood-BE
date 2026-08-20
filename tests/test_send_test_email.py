from typing import Any

import pytest
from backend.config.email import EmailService
from scripts import send_test_email as test_email_script


@pytest.mark.asyncio
async def test_script_sends_to_fixed_test_recipient(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sent: dict[str, Any] = {}

    async def fake_send_email(service: EmailService, **message: Any) -> int:
        sent.update(message)
        return 202

    monkeypatch.setenv("SENDGRID_API_KEY", "sendgrid-api-key")
    monkeypatch.setenv("SENDGRID_FROM_EMAIL", "verified-sender@example.com")
    monkeypatch.setattr(EmailService, "send_email", fake_send_email)

    await test_email_script.send_test_email()

    assert sent["from_email"] == "verified-sender@example.com"
    assert sent["to_emails"] == "aghabekyan.pargev@gmail.com"
    assert sent["subject"] == "NutriFood SendGrid test"
    assert "HTTP 202" in capsys.readouterr().out
