from typing import Any
from uuid import UUID

from backend.apps.admin.security import hash_admin_password
from backend.config.database import get_pool
from backend.config.settings import Settings, get_settings
from fastapi.testclient import TestClient

ADMIN_ID = UUID("40000000-0000-0000-0000-000000000001")
ADMIN_USERNAME = "admin@mail.com"
ADMIN_PASSWORD = "123456"


class FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def eval(self, _script: str, numkeys: int, *args: object) -> list[int]:
        keys = [str(value) for value in args[:numkeys]]
        values = []
        for key in keys:
            self.counts[key] = self.counts.get(key, 0) + 1
            values.append(self.counts[key])
        return values


class DummyPool:
    async def close(self) -> None:
        return None


class AdminAuthPool:
    def __init__(self, *, is_active: bool = True, token_version: int = 1) -> None:
        self.record: dict[str, object] = {
            "id": ADMIN_ID,
            "username": ADMIN_USERNAME,
            "password_hash": hash_admin_password(ADMIN_PASSWORD),
            "is_active": is_active,
            "token_version": token_version,
        }
        self.last_login_admin_id: UUID | None = None
        self.last_refresh_admin_id: UUID | None = None
        self.refresh_sessions: dict[str, dict[str, object]] = {}

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "WHERE username = $1" in query:
            return self.record if args == (ADMIN_USERNAME,) else None
        if "WHERE id = $1" in query:
            return self.record if args == (ADMIN_ID,) else None
        if "UPDATE admin_refresh_sessions" in query:
            jti_hash, admin_id, family_id = args
            session = self.refresh_sessions.get(str(jti_hash))
            if (
                session is not None
                and session["admin_id"] == admin_id
                and session["family_id"] == family_id
                and not session["consumed"]
                and not session["revoked"]
            ):
                session["consumed"] = True
                return {"jti_hash": jti_hash}
            return None

        raise AssertionError(f"Unexpected query: {query}")

    async def execute(self, query: str, *args: object) -> str:
        if "last_login_at" in query:
            self.last_login_admin_id = args[0] if isinstance(args[0], UUID) else None
            return "UPDATE 1"
        if "last_refresh_at" in query:
            self.last_refresh_admin_id = args[0] if isinstance(args[0], UUID) else None
            return "UPDATE 1"
        if "INSERT INTO admin_refresh_sessions" in query:
            jti_hash, admin_id, family_id, expires_at = args
            self.refresh_sessions[str(jti_hash)] = {
                "admin_id": admin_id,
                "family_id": family_id,
                "expires_at": expires_at,
                "consumed": False,
                "revoked": False,
            }
            return "INSERT 0 1"
        if "UPDATE admin_refresh_sessions" in query and "revoked_at" in query:
            admin_id, family_id = args
            for session in self.refresh_sessions.values():
                if session["admin_id"] == admin_id and session["family_id"] == family_id:
                    session["revoked"] = True
            return "UPDATE 1"

        raise AssertionError(f"Unexpected query: {query}")


async def create_dummy_pool() -> DummyPool:
    return DummyPool()


def configured_settings() -> Settings:
    return Settings(
        admin_username=ADMIN_USERNAME,
        admin_password=ADMIN_PASSWORD,
        admin_token_secret="test-admin-token-secret-with-at-least-32-bytes",
        admin_access_token_expire_minutes=30,
        admin_refresh_token_expire_days=14,
    )


def configure_test_app(monkeypatch: Any, pool: AdminAuthPool) -> Any:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    app.dependency_overrides[get_settings] = configured_settings
    app.dependency_overrides[get_pool] = lambda: pool
    from backend.config.cache import get_cache_client

    app.dependency_overrides[get_cache_client] = lambda: FakeRedis()
    return app


def test_admin_login_returns_access_and_refresh_tokens(monkeypatch: Any) -> None:
    pool = AdminAuthPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/auth/login",
                json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 1_800
    assert body["refresh_expires_in"] == 1_209_600
    assert body["access_token"]
    assert body["refresh_token"]
    assert pool.last_login_admin_id == ADMIN_ID


def test_admin_sign_in_accepts_email_field(monkeypatch: Any) -> None:
    pool = AdminAuthPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/auth/sign-in",
                json={"email": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert pool.last_login_admin_id == ADMIN_ID


def test_admin_access_token_authorizes_admin_endpoints(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, AdminAuthPool())

    try:
        with TestClient(app) as client:
            login_response = client.post(
                "/api/v1/admin/auth/login",
                json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            )
            token = str(login_response.json()["access_token"])
            response = client.get("/api/v1/admin", headers={"Authorization": f"Bearer {token}"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"module": "admin", "status": "ready"}


def test_admin_refresh_token_rotates_token_pair(monkeypatch: Any) -> None:
    pool = AdminAuthPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            login_response = client.post(
                "/api/v1/admin/auth/login",
                json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            )
            refresh_token = str(login_response.json()["refresh_token"])
            refresh_response = client.post(
                "/api/v1/admin/auth/refresh",
                json={"refresh_token": refresh_token},
            )
            access_token = str(refresh_response.json()["access_token"])
            protected_response = client.get(
                "/api/v1/admin",
                headers={"Authorization": f"Bearer {access_token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert refresh_response.status_code == 200
    assert refresh_response.json()["access_token"]
    assert refresh_response.json()["refresh_token"]
    assert protected_response.status_code == 200
    assert pool.last_refresh_admin_id == ADMIN_ID


def test_admin_refresh_token_replay_revokes_family(monkeypatch: Any) -> None:
    pool = AdminAuthPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            login_response = client.post(
                "/api/v1/admin/auth/login",
                json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            )
            refresh_token = str(login_response.json()["refresh_token"])
            first_refresh = client.post(
                "/api/v1/admin/auth/refresh", json={"refresh_token": refresh_token}
            )
            replay = client.post(
                "/api/v1/admin/auth/refresh", json={"refresh_token": refresh_token}
            )
    finally:
        app.dependency_overrides.clear()

    assert first_refresh.status_code == 200
    assert replay.status_code == 401


def test_admin_login_rejects_invalid_credentials(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, AdminAuthPool())

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/auth/login",
                json={"username": ADMIN_USERNAME, "password": "wrong-password"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid admin credentials"}


def test_admin_endpoint_requires_bearer_token(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, AdminAuthPool())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/admin")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Admin authentication required"}
