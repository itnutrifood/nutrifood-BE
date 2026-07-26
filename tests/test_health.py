from typing import Any

from fastapi.testclient import TestClient


class DummyPool:
    async def close(self) -> None:
        return None


async def create_dummy_pool() -> DummyPool:
    return DummyPool()


def test_health(monkeypatch: Any) -> None:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_versioned_status_routes(monkeypatch: Any) -> None:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)

    with TestClient(app) as client:
        v1_response = client.get("/api/v1/status")
        v2_response = client.get("/api/v2/status")

    assert v1_response.status_code == 200
    assert v1_response.json() == {"status": "ok", "version": "v1"}
    assert v2_response.status_code == 200
    assert v2_response.json() == {"status": "ok", "version": "v2"}


def test_swagger_ui_persists_authorization(monkeypatch: Any) -> None:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)

    with TestClient(app) as client:
        response = client.get("/docs")

    assert response.status_code == 200
    assert '"persistAuthorization": true' in response.text


def test_cors_preflight_allows_configured_origin(monkeypatch: Any) -> None:
    from backend.config import database
    from backend.config.asgi import app, settings

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    origin = settings.cors_origins[0]

    with TestClient(app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
