from types import SimpleNamespace
from typing import Any

import pytest
from backend.config.firebase import (
    FirebaseService,
    create_firebase_service,
    get_firebase_service,
)
from backend.config.settings import Settings
from firebase_admin import auth, messaging


@pytest.mark.asyncio
async def test_verify_id_token_checks_revocation(monkeypatch: Any) -> None:
    firebase_app = object()
    captured: dict[str, object] = {}

    def fake_verify_id_token(
        id_token: str,
        *,
        app: object,
        check_revoked: bool,
    ) -> dict[str, object]:
        captured.update(id_token=id_token, app=app, check_revoked=check_revoked)
        return {"uid": "firebase-user-uid"}

    monkeypatch.setattr(auth, "verify_id_token", fake_verify_id_token)
    service = FirebaseService(firebase_app)

    claims = await service.verify_id_token("firebase-id-token")

    assert claims == {"uid": "firebase-user-uid"}
    assert captured == {
        "id_token": "firebase-id-token",
        "app": firebase_app,
        "check_revoked": True,
    }


@pytest.mark.asyncio
async def test_send_notification_builds_fid_message(monkeypatch: Any) -> None:
    firebase_app = object()
    sent: dict[str, object] = {}

    def fake_send(
        message: messaging.Message,
        *,
        dry_run: bool,
        app: object,
    ) -> str:
        sent.update(message=message, dry_run=dry_run, app=app)
        return "projects/nutrifood/messages/message-id"

    monkeypatch.setattr(messaging, "send", fake_send)
    service = FirebaseService(firebase_app)

    message_id = await service.send_notification(
        fid="firebase-installation-id",
        title="Order ready",
        body="Your order is ready for pickup.",
        data={"order_id": "order-123"},
        image_url="https://cdn.example.test/order-ready.png",
        dry_run=True,
    )

    message = sent["message"]
    assert isinstance(message, messaging.Message)
    assert message.fid == "firebase-installation-id"
    assert message.notification.title == "Order ready"
    assert message.notification.body == "Your order is ready for pickup."
    assert message.notification.image == "https://cdn.example.test/order-ready.png"
    assert message.data == {"order_id": "order-123"}
    assert sent["dry_run"] is True
    assert sent["app"] is firebase_app
    assert message_id == "projects/nutrifood/messages/message-id"


def test_create_firebase_service_uses_configured_credentials(monkeypatch: Any) -> None:
    firebase_app = object()
    captured: dict[str, object] = {}

    def fake_certificate(path: str) -> object:
        captured["credential_path"] = path
        return "credential"

    def fake_initialize_app(
        *,
        credential: object,
        options: dict[str, str] | None,
        name: str,
    ) -> object:
        captured.update(credential=credential, options=options, name=name)
        return firebase_app

    monkeypatch.setattr("backend.config.firebase.credentials.Certificate", fake_certificate)
    monkeypatch.setattr(
        "backend.config.firebase.firebase_admin.initialize_app",
        fake_initialize_app,
    )
    settings = Settings(
        _env_file=None,
        firebase_credentials_path="/run/secrets/firebase.json",
        firebase_project_id="nutrifood-production",
    )

    service = create_firebase_service(settings)

    assert captured == {
        "credential_path": "/run/secrets/firebase.json",
        "credential": "credential",
        "options": {"projectId": "nutrifood-production"},
        "name": "nutrifood",
    }
    assert service._app is firebase_app


def test_close_deletes_firebase_app_once(monkeypatch: Any) -> None:
    firebase_app = object()
    deleted: list[object] = []
    monkeypatch.setattr("backend.config.firebase.firebase_admin.delete_app", deleted.append)
    service = FirebaseService(firebase_app)

    service.close()
    service.close()

    assert deleted == [firebase_app]


def test_get_firebase_service_reads_application_state() -> None:
    service = FirebaseService(object())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(firebase_service=service)))

    assert get_firebase_service(request) is service
