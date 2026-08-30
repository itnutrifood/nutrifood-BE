from typing import Any

from fastapi.testclient import TestClient


class DummyPool:
    async def close(self) -> None:
        return None


async def create_dummy_pool() -> DummyPool:
    return DummyPool()


def test_request_validation_does_not_reflect_admin_password(monkeypatch: Any) -> None:
    from backend.config import database
    from backend.config.asgi import app

    marker = "validation-only-password-marker"
    monkeypatch.setattr(database, "create_pool", create_dummy_pool)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/auth/login",
            json={"password": marker},
        )

    assert response.status_code == 422
    assert marker not in response.text
    assert all("input" not in error for error in response.json()["detail"])
