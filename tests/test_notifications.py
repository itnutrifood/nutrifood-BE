from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import UUID

from backend.apps.accounts.auth import UserIdentity, get_current_user
from backend.config.database import get_pool
from backend.config.firebase import get_firebase_service
from backend.config.settings import Settings, get_settings
from fastapi.testclient import TestClient
from firebase_admin import messaging

USER_ID = UUID("50000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 1, 1, tzinfo=UTC)
FCM_TOKEN = "fcm-registration-token-at-least-twenty-characters"
FIREBASE_FID = "firebase-installation-id-at-least-twenty-characters"


def registration_hash(registration_type: str, registration_id: str) -> bytes:
    return sha256(f"{registration_type}\0{registration_id}".encode()).digest()


class DummyPool:
    async def close(self) -> None:
        return None


class DummyFirebaseLifecycle:
    def close(self) -> None:
        return None


class FcmTokenPool:
    def __init__(self, registration: dict[str, object] | None = None) -> None:
        self.registered: tuple[object, ...] | None = None
        self.removed: tuple[object, ...] | None = None
        self.registration = registration
        self.registration_fetched = False

    async def execute(self, query: str, *args: object) -> str:
        if "INSERT INTO user_fcm_registrations" in query:
            assert "ON CONFLICT (registration_hash) DO UPDATE" in query
            assert "last_seen_at = now()" in query
            self.registered = args
            return "INSERT 0 1"

        if "DELETE FROM user_fcm_registrations" in query:
            assert "registration_type = $3" in query
            assert "user_id = $4" in query
            self.removed = args
            return "DELETE 1"

        raise AssertionError(f"Unexpected query: {query}")

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "FROM user_fcm_registrations" in query
        assert "last_seen_at DESC" in query
        assert args == (USER_ID,)
        self.registration_fetched = True
        return self.registration


class FakeFirebaseService:
    def __init__(self) -> None:
        self.message: messaging.Message | None = None

    async def send(self, message: messaging.Message, *, dry_run: bool = False) -> str:
        assert dry_run is False
        self.message = message
        return "projects/nutrifood/messages/test-message-id"


async def create_dummy_pool() -> DummyPool:
    return DummyPool()


def current_user() -> UserIdentity:
    return UserIdentity(
        id=USER_ID,
        firebase_uid="firebase-user-uid",
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        sign_in_provider="google.com",
        roles=frozenset(),
        created_at=NOW,
        updated_at=NOW,
    )


def configure_test_app(
    monkeypatch: Any,
    pool: FcmTokenPool,
    *,
    authenticated: bool = True,
    environment: str = "local",
    firebase_service: FakeFirebaseService | None = None,
) -> Any:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    monkeypatch.setattr(
        database,
        "create_firebase_service",
        lambda: DummyFirebaseLifecycle(),
    )
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        environment=environment,
    )
    app.dependency_overrides[get_firebase_service] = lambda: (
        firebase_service or FakeFirebaseService()
    )
    if authenticated:
        app.dependency_overrides[get_current_user] = current_user
    return app


def test_send_test_notification_to_current_users_latest_registration(
    monkeypatch: Any,
) -> None:
    pool = FcmTokenPool(
        registration={
            "registration_id": FIREBASE_FID,
            "registration_type": "fid",
        }
    )
    firebase_service = FakeFirebaseService()
    app = configure_test_app(
        monkeypatch,
        pool,
        firebase_service=firebase_service,
    )

    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/notifications/test")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"message_id": "projects/nutrifood/messages/test-message-id"}
    assert pool.registration_fetched is True
    assert firebase_service.message is not None
    assert firebase_service.message.fid == FIREBASE_FID
    assert firebase_service.message.notification.title == "NutriFood test notification"
    assert (
        firebase_service.message.notification.body
        == "Firebase Cloud Messaging is configured correctly."
    )
    assert firebase_service.message.data == {"type": "test_notification"}


def test_send_test_notification_requires_registration(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, FcmTokenPool())

    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/notifications/test")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "No FCM registration found for the current user"}


def test_send_test_notification_is_hidden_in_production(monkeypatch: Any) -> None:
    pool = FcmTokenPool(
        registration={
            "registration_id": FIREBASE_FID,
            "registration_type": "fid",
        }
    )
    firebase_service = FakeFirebaseService()
    app = configure_test_app(
        monkeypatch,
        pool,
        environment="production",
        firebase_service=firebase_service,
    )

    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/notifications/test")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert pool.registration_fetched is False
    assert firebase_service.message is None


def test_send_test_notification_requires_authentication(monkeypatch: Any) -> None:
    app = configure_test_app(
        monkeypatch,
        FcmTokenPool(),
        authenticated=False,
    )

    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/notifications/test")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_register_firebase_installation_is_authenticated_and_idempotent(
    monkeypatch: Any,
) -> None:
    pool = FcmTokenPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/notifications/fcm-registrations",
                json={"fid": FIREBASE_FID, "platform": "android"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert pool.registered == (
        registration_hash("fid", FIREBASE_FID),
        FIREBASE_FID,
        "fid",
        USER_ID,
        "android",
    )


def test_unregister_firebase_installation_scopes_delete_to_current_user(
    monkeypatch: Any,
) -> None:
    pool = FcmTokenPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.request(
                "DELETE",
                "/api/v1/notifications/fcm-registrations",
                json={"fid": FIREBASE_FID},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert pool.removed == (
        registration_hash("fid", FIREBASE_FID),
        FIREBASE_FID,
        "fid",
        USER_ID,
    )


def test_legacy_fcm_token_endpoint_remains_supported(monkeypatch: Any) -> None:
    pool = FcmTokenPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/notifications/fcm-tokens",
                json={"token": FCM_TOKEN, "platform": "ios"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert pool.registered == (
        registration_hash("token", FCM_TOKEN),
        FCM_TOKEN,
        "token",
        USER_ID,
        "ios",
    )


def test_fcm_token_endpoint_rejects_unsupported_platform(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, FcmTokenPool())

    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/notifications/fcm-registrations",
                json={"fid": FIREBASE_FID, "platform": "desktop"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_fcm_token_endpoint_requires_authentication(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, FcmTokenPool(), authenticated=False)

    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/v1/notifications/fcm-registrations",
                json={"fid": FIREBASE_FID, "platform": "ios"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
