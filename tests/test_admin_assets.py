from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from uuid import UUID

from backend.apps.admin import auth as admin_auth_module
from backend.apps.assets.dependencies import get_asset_storage
from backend.apps.assets.exceptions import AssetUploadNotFoundError
from backend.apps.assets.storage import ObjectMetadata
from backend.config.database import get_pool
from fastapi.testclient import TestClient
from PIL import Image

ADMIN_ID = UUID("40000000-0000-0000-0000-000000000001")
UPLOAD_ID = UUID("50000000-0000-0000-0000-000000000001")


class DummyPool:
    async def close(self) -> None:
        return None


async def create_dummy_pool() -> DummyPool:
    return DummyPool()


def png_bytes(width: int = 32, height: int = 24) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), color=(40, 120, 80)).save(output, format="PNG")
    return output.getvalue()


class FakeAssetStorage:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.created_upload: tuple[str, str, int] | None = None
        self.promoted: tuple[str, str, str] | None = None
        self.deleted: list[str] = []
        self.staging_exists = True
        self.final_exists = False

    def create_upload_url(self, object_key: str, content_type: str, expires_in: int) -> str:
        self.created_upload = (object_key, content_type, expires_in)
        return "https://r2.example.test/presigned-put"

    def public_url(self, object_key: str) -> str:
        return f"https://assets.example.test/{object_key}"

    async def head_object(self, object_key: str) -> ObjectMetadata:
        if object_key.startswith("pending/") and not self.staging_exists:
            raise AssetUploadNotFoundError
        if object_key.startswith("products/images/") and not self.final_exists:
            raise AssetUploadNotFoundError
        return ObjectMetadata(
            content_type="image/png",
            size_bytes=len(self.data),
            etag='"test-etag"',
        )

    async def read_object(self, object_key: str, etag: str, max_bytes: int) -> bytes:
        assert etag == '"test-etag"'
        assert max_bytes == 5 * 1024 * 1024
        return self.data

    async def promote_object(
        self,
        source_key: str,
        destination_key: str,
        content_type: str,
    ) -> None:
        self.promoted = (source_key, destination_key, content_type)
        self.staging_exists = False
        self.final_exists = True

    async def delete_object(self, object_key: str) -> None:
        self.deleted.append(object_key)


def configure_test_app(monkeypatch: Any, storage: FakeAssetStorage) -> Any:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    app.dependency_overrides[admin_auth_module.admin_auth] = lambda: admin_auth_module.AdminUser(
        id=ADMIN_ID,
        username="admin@mail.com",
        token_version=1,
    )
    app.dependency_overrides[get_pool] = lambda: DummyPool()
    app.dependency_overrides[get_asset_storage] = lambda: storage
    return app


def test_admin_can_create_product_image_upload(monkeypatch: Any) -> None:
    from backend.apps.assets import service

    monkeypatch.setattr(service, "uuid4", lambda: UPLOAD_ID)
    storage = FakeAssetStorage(png_bytes())
    app = configure_test_app(monkeypatch, storage)

    before_request = datetime.now(UTC)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/assets/uploads",
                json={
                    "purpose": "product_image",
                    "content_type": "image/png",
                    "size_bytes": len(storage.data),
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["upload_id"] == str(UPLOAD_ID)
    assert response.json()["purpose"] == "product_image"
    assert response.json()["upload_url"] == "https://r2.example.test/presigned-put"
    assert response.json()["method"] == "PUT"
    assert response.json()["headers"] == {"Content-Type": "image/png"}
    assert datetime.fromisoformat(response.json()["expires_at"]) > before_request
    assert storage.created_upload == (
        f"pending/products/images/{UPLOAD_ID}",
        "image/png",
        900,
    )


def test_admin_can_complete_product_image_upload(monkeypatch: Any) -> None:
    data = png_bytes(width=120, height=90)
    storage = FakeAssetStorage(data)
    app = configure_test_app(monkeypatch, storage)

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/admin/assets/uploads/{UPLOAD_ID}/complete",
                json={
                    "purpose": "product_image",
                    "content_type": "image/png",
                    "size_bytes": len(data),
                },
            )
    finally:
        app.dependency_overrides.clear()

    final_key = f"products/images/{UPLOAD_ID}.png"
    assert response.status_code == 200
    assert response.json() == {
        "id": str(UPLOAD_ID),
        "purpose": "product_image",
        "object_key": final_key,
        "url": f"https://assets.example.test/{final_key}",
        "content_type": "image/png",
        "size_bytes": len(data),
        "metadata": {"type": "image", "width": 120, "height": 90},
    }
    assert storage.promoted == (
        f"pending/products/images/{UPLOAD_ID}",
        final_key,
        "image/png",
    )


def test_completing_product_image_upload_is_idempotent(monkeypatch: Any) -> None:
    data = png_bytes()
    storage = FakeAssetStorage(data)
    storage.staging_exists = False
    storage.final_exists = True
    app = configure_test_app(monkeypatch, storage)

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/admin/assets/uploads/{UPLOAD_ID}/complete",
                json={
                    "purpose": "product_image",
                    "content_type": "image/png",
                    "size_bytes": len(data),
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["metadata"]["width"] == 32
    assert storage.promoted is None


def test_complete_product_image_rejects_disguised_file(monkeypatch: Any) -> None:
    storage = FakeAssetStorage(b"this is not a PNG")
    app = configure_test_app(monkeypatch, storage)

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/admin/assets/uploads/{UPLOAD_ID}/complete",
                json={
                    "purpose": "product_image",
                    "content_type": "image/png",
                    "size_bytes": len(storage.data),
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json() == {"detail": "Uploaded file is not a valid image"}
    assert storage.deleted == [f"pending/products/images/{UPLOAD_ID}"]
    assert storage.promoted is None


def test_complete_product_image_rejects_size_mismatch(monkeypatch: Any) -> None:
    storage = FakeAssetStorage(png_bytes())
    app = configure_test_app(monkeypatch, storage)

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/admin/assets/uploads/{UPLOAD_ID}/complete",
                json={
                    "purpose": "product_image",
                    "content_type": "image/png",
                    "size_bytes": len(storage.data) - 1,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json() == {"detail": "Uploaded asset size does not match the request"}
    assert storage.deleted == [f"pending/products/images/{UPLOAD_ID}"]


def test_product_image_upload_rejects_unsupported_content_type(monkeypatch: Any) -> None:
    storage = FakeAssetStorage(png_bytes())
    app = configure_test_app(monkeypatch, storage)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/assets/uploads",
                json={
                    "purpose": "product_image",
                    "content_type": "image/svg+xml",
                    "size_bytes": 1000,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert storage.created_upload is None


def test_product_image_policy_rejects_oversized_asset(monkeypatch: Any) -> None:
    storage = FakeAssetStorage(png_bytes())
    app = configure_test_app(monkeypatch, storage)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/assets/uploads",
                json={
                    "purpose": "product_image",
                    "content_type": "image/png",
                    "size_bytes": 5 * 1024 * 1024 + 1,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json() == {"detail": "Asset exceeds the 5 MiB limit"}
    assert storage.created_upload is None
