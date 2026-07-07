from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from backend.apps.common.security import hash_password
from backend.config.database import get_pool
from backend.config.settings import Settings, get_settings
from fastapi.testclient import TestClient

USER_ID = UUID("50000000-0000-0000-0000-000000000001")
USER_EMAIL = "jane@example.com"
USER_PASSWORD = "correct-password"
CREATED_AT = datetime(2026, 1, 1, tzinfo=UTC)


class DummyPool:
    async def close(self) -> None:
        return None


class UserAuthPool:
    def __init__(self, *, is_active: bool = True) -> None:
        self.record: dict[str, object] | None = {
            "id": USER_ID,
            "first_name": "Jane",
            "last_name": "Doe",
            "email": USER_EMAIL,
            "password_hash": hash_password(USER_PASSWORD),
            "is_active": is_active,
            "token_version": 1,
            "created_at": CREATED_AT,
            "updated_at": CREATED_AT,
        }
        self.last_login_user_id: UUID | None = None
        self.last_refresh_user_id: UUID | None = None

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "INSERT INTO users" in query:
            self.record = {
                "id": USER_ID,
                "first_name": args[0],
                "last_name": args[1],
                "email": args[2],
                "password_hash": args[3],
                "is_active": True,
                "token_version": 1,
                "created_at": CREATED_AT,
                "updated_at": CREATED_AT,
            }
            return self.record

        if "WHERE email = $1" in query:
            if self.record is None:
                return None
            return self.record if args == (self.record["email"],) else None

        if "WHERE id = $1" in query:
            if self.record is None:
                return None
            return self.record if args == (self.record["id"],) else None

        raise AssertionError(f"Unexpected query: {query}")

    async def execute(self, query: str, *args: object) -> str:
        if "last_login_at" in query:
            self.last_login_user_id = args[0] if isinstance(args[0], UUID) else None
            return "UPDATE 1"

        if "last_refresh_at" in query:
            self.last_refresh_user_id = args[0] if isinstance(args[0], UUID) else None
            return "UPDATE 1"

        raise AssertionError(f"Unexpected query: {query}")


async def create_dummy_pool() -> DummyPool:
    return DummyPool()


def configured_settings() -> Settings:
    return Settings(
        user_token_secret="test-user-token-secret-with-at-least-32-bytes",
        user_access_token_expire_minutes=30,
        user_refresh_token_expire_days=14,
    )


def configure_test_app(monkeypatch: Any, pool: UserAuthPool) -> Any:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    app.dependency_overrides[get_settings] = configured_settings
    app.dependency_overrides[get_pool] = lambda: pool
    return app


def test_user_signup_returns_tokens_and_created_user(monkeypatch: Any) -> None:
    pool = UserAuthPool()
    pool.record = None
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/accounts/auth/signup",
                json={
                    "first_name": "Jane",
                    "last_name": "Doe",
                    "email": "Jane@Example.COM",
                    "password": USER_PASSWORD,
                    "confirm_password": USER_PASSWORD,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 1_800
    assert body["refresh_expires_in"] == 1_209_600
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"] == {
        "id": str(USER_ID),
        "first_name": "Jane",
        "last_name": "Doe",
        "email": USER_EMAIL,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    assert pool.record is not None
    assert pool.record["email"] == USER_EMAIL
    assert pool.record["password_hash"] != USER_PASSWORD


def test_user_login_returns_tokens_and_updates_last_login(monkeypatch: Any) -> None:
    pool = UserAuthPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/accounts/auth/login",
                json={"email": "Jane@Example.COM", "password": USER_PASSWORD},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["email"] == USER_EMAIL
    assert pool.last_login_user_id == USER_ID


def test_user_access_token_authorizes_me(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, UserAuthPool())

    try:
        with TestClient(app) as client:
            login_response = client.post(
                "/api/v1/accounts/auth/login",
                json={"email": USER_EMAIL, "password": USER_PASSWORD},
            )
            token = str(login_response.json()["access_token"])
            response = client.get(
                "/api/v1/accounts/me",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["email"] == USER_EMAIL


def test_user_refresh_token_rotates_token_pair(monkeypatch: Any) -> None:
    pool = UserAuthPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            login_response = client.post(
                "/api/v1/accounts/auth/login",
                json={"email": USER_EMAIL, "password": USER_PASSWORD},
            )
            refresh_token = str(login_response.json()["refresh_token"])
            refresh_response = client.post(
                "/api/v1/accounts/auth/refresh",
                json={"refresh_token": refresh_token},
            )
            access_token = str(refresh_response.json()["access_token"])
            protected_response = client.get(
                "/api/v1/accounts/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert refresh_response.status_code == 200
    assert refresh_response.json()["access_token"]
    assert refresh_response.json()["refresh_token"]
    assert protected_response.status_code == 200
    assert pool.last_refresh_user_id == USER_ID


def test_user_login_rejects_invalid_credentials(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, UserAuthPool())

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/accounts/auth/login",
                json={"email": USER_EMAIL, "password": "wrong-password"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}


def test_user_signup_requires_matching_password_confirmation(monkeypatch: Any) -> None:
    pool = UserAuthPool()
    pool.record = None
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/accounts/auth/signup",
                json={
                    "first_name": "Jane",
                    "last_name": "Doe",
                    "email": USER_EMAIL,
                    "password": USER_PASSWORD,
                    "confirm_password": "different-password",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_accounts_me_requires_bearer_token(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, UserAuthPool())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/accounts/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
