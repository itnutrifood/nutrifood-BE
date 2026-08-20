from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from backend.apps.accounts.auth import RoleChecker, UserIdentity
from backend.config.database import get_pool
from backend.config.firebase import get_firebase_service
from backend.config.settings import Settings, get_settings
from fastapi import HTTPException
from fastapi.testclient import TestClient
from firebase_admin import auth

USER_ID = UUID("50000000-0000-0000-0000-000000000001")
FIREBASE_UID = "firebase-user-uid"
USER_EMAIL = "jane@example.com"
CREATED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def user_record(
    *,
    firebase_uid: str | None = FIREBASE_UID,
    is_active: bool = True,
    registration_provider: str = "password",
) -> dict[str, object]:
    return {
        "id": USER_ID,
        "firebase_uid": firebase_uid,
        "first_name": "Jane",
        "last_name": "Doe",
        "email": USER_EMAIL,
        "registration_provider": registration_provider,
        "is_active": is_active,
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }


def firebase_claims(
    *,
    provider: str = "password",
    email_verified: bool = True,
    roles: list[str] | None = None,
) -> dict[str, object]:
    return {
        "uid": FIREBASE_UID,
        "sub": FIREBASE_UID,
        "email": USER_EMAIL,
        "email_verified": email_verified,
        "given_name": "Jane",
        "family_name": "Doe",
        "firebase": {"sign_in_provider": provider},
        "roles": roles or [],
    }


class DummyPool:
    async def close(self) -> None:
        return None


class DummyFirebaseLifecycle:
    def close(self) -> None:
        return None


class FakeFirebaseService:
    def __init__(
        self,
        *,
        claims: dict[str, object] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.claims = claims or firebase_claims()
        self.error = error
        self.verified_token: str | None = None

    async def verify_id_token(self, id_token: str) -> dict[str, object]:
        self.verified_token = id_token
        if self.error is not None:
            raise self.error
        return self.claims


class FirebaseAuthPool:
    def __init__(self, record: dict[str, object] | None = None) -> None:
        self.record = user_record() if record is None else record
        self.created_args: tuple[object, ...] | None = None
        self.linked_args: tuple[object, ...] | None = None
        self.synced_query: str | None = None
        self.synced_args: tuple[object, ...] | None = None

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "WHERE firebase_uid = $1" in query:
            if self.record is None:
                return None
            return self.record if args == (self.record["firebase_uid"],) else None

        if "WHERE email = $1" in query:
            if self.record is None:
                return None
            return self.record if args == (self.record["email"],) else None

        if "INSERT INTO users" in query:
            self.created_args = args
            self.record = user_record(
                firebase_uid=str(args[0]),
                registration_provider=str(args[4]),
            )
            return self.record

        if "SET firebase_uid = $2" in query:
            self.linked_args = args
            if self.record is None:
                return None
            self.record["firebase_uid"] = args[1]
            return self.record

        if "SET email = $2" in query:
            self.synced_query = query
            self.synced_args = args
            # The real query returns no row when the Firebase profile is unchanged.
            return None

        raise AssertionError(f"Unexpected query: {query}")


class EmptyFirebaseAuthPool(FirebaseAuthPool):
    def __init__(self) -> None:
        self.record = None
        self.created_args = None
        self.linked_args = None


async def create_dummy_pool() -> DummyPool:
    return DummyPool()


def configured_settings() -> Settings:
    return Settings(
        _env_file=None,
        firebase_project_id="nutrifood-test",
        firebase_require_verified_email=True,
        firebase_allowed_sign_in_providers={"password", "google.com"},
    )


def configure_test_app(
    monkeypatch: Any,
    pool: FirebaseAuthPool,
    firebase_service: FakeFirebaseService | None = None,
) -> tuple[Any, FakeFirebaseService]:
    from backend.config import database
    from backend.config.asgi import app

    service = firebase_service or FakeFirebaseService()
    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    monkeypatch.setattr(
        database,
        "create_firebase_service",
        lambda: DummyFirebaseLifecycle(),
    )
    app.dependency_overrides[get_settings] = configured_settings
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_firebase_service] = lambda: service
    return app, service


def test_firebase_password_token_authorizes_existing_user(monkeypatch: Any) -> None:
    app, service = configure_test_app(monkeypatch, FirebaseAuthPool())

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/accounts/me",
                headers={"Authorization": "Bearer firebase-id-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "id": str(USER_ID),
        "first_name": "Jane",
        "last_name": "Doe",
        "email": USER_EMAIL,
        "registration_provider": "password",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    assert service.verified_token == "firebase-id-token"


def test_firebase_google_token_creates_local_user(monkeypatch: Any) -> None:
    pool = EmptyFirebaseAuthPool()
    service = FakeFirebaseService(claims=firebase_claims(provider="google.com"))
    app, _ = configure_test_app(monkeypatch, pool, service)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/accounts/auth/session",
                headers={"Authorization": "Bearer google-firebase-id-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["email"] == USER_EMAIL
    assert response.json()["registration_provider"] == "google.com"
    assert pool.created_args == (
        FIREBASE_UID,
        "Jane",
        "Doe",
        USER_EMAIL,
        "google.com",
    )


def test_firebase_password_token_creates_user_with_registration_provider(
    monkeypatch: Any,
) -> None:
    pool = EmptyFirebaseAuthPool()
    app, _ = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/accounts/auth/session",
                headers={"Authorization": "Bearer password-firebase-id-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["registration_provider"] == "password"
    assert pool.created_args == (
        FIREBASE_UID,
        "Jane",
        "Doe",
        USER_EMAIL,
        "password",
    )


def test_verified_firebase_email_links_legacy_user(monkeypatch: Any) -> None:
    pool = FirebaseAuthPool(record=user_record(firebase_uid=None))
    app, _ = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/accounts/auth/session",
                headers={"Authorization": "Bearer firebase-id-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["registration_provider"] == "password"
    assert pool.linked_args == (USER_ID, FIREBASE_UID, "Jane", "Doe")


def test_later_login_does_not_change_registration_provider(monkeypatch: Any) -> None:
    pool = FirebaseAuthPool(record=user_record(registration_provider="password"))
    service = FakeFirebaseService(claims=firebase_claims(provider="google.com"))
    app, _ = configure_test_app(monkeypatch, pool, service)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/accounts/auth/session",
                headers={"Authorization": "Bearer google-firebase-id-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["registration_provider"] == "password"
    assert pool.record is not None
    assert pool.record["registration_provider"] == "password"
    assert pool.synced_args == (USER_ID, USER_EMAIL, "Jane", "Doe")
    assert pool.synced_query is not None
    assert "$3::varchar IS NOT NULL" in pool.synced_query
    assert "$4::varchar IS NOT NULL" in pool.synced_query


def test_accounts_me_requires_bearer_token(monkeypatch: Any) -> None:
    app, service = configure_test_app(monkeypatch, FirebaseAuthPool())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/accounts/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
    assert response.headers["www-authenticate"] == "Bearer"
    assert service.verified_token is None


def test_invalid_firebase_token_is_rejected(monkeypatch: Any) -> None:
    service = FakeFirebaseService(error=auth.InvalidIdTokenError("invalid"))
    app, _ = configure_test_app(monkeypatch, FirebaseAuthPool(), service)

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/accounts/me",
                headers={"Authorization": "Bearer invalid-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid Firebase ID token"}


def test_unverified_email_is_rejected(monkeypatch: Any) -> None:
    service = FakeFirebaseService(claims=firebase_claims(email_verified=False))
    app, _ = configure_test_app(monkeypatch, FirebaseAuthPool(), service)

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/accounts/me",
                headers={"Authorization": "Bearer firebase-id-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Email verification is required"}


def test_disallowed_sign_in_provider_is_rejected(monkeypatch: Any) -> None:
    service = FakeFirebaseService(claims=firebase_claims(provider="anonymous"))
    app, _ = configure_test_app(monkeypatch, FirebaseAuthPool(), service)

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/accounts/me",
                headers={"Authorization": "Bearer firebase-id-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Sign-in provider is not allowed"}


def test_disabled_local_user_is_rejected(monkeypatch: Any) -> None:
    app, _ = configure_test_app(
        monkeypatch,
        FirebaseAuthPool(record=user_record(is_active=False)),
    )

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/accounts/me",
                headers={"Authorization": "Bearer firebase-id-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "User account is disabled"}


@pytest.mark.asyncio
async def test_role_checker_requires_all_custom_claim_roles() -> None:
    user = UserIdentity(
        id=USER_ID,
        firebase_uid=FIREBASE_UID,
        first_name="Jane",
        last_name="Doe",
        email=USER_EMAIL,
        registration_provider="google.com",
        sign_in_provider="google.com",
        roles=frozenset({"subscriber", "beta"}),
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )

    assert await RoleChecker("subscriber", "beta")(user) is user
    with pytest.raises(HTTPException) as exception:
        await RoleChecker("admin")(user)

    assert exception.value.status_code == 403
