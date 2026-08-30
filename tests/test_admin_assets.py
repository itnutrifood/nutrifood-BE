from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from uuid import UUID

import pytest
from backend.apps.admin import auth as admin_auth_module
from backend.apps.assets import storage as storage_module
from backend.apps.assets.dependencies import get_asset_storage
from backend.apps.assets.exceptions import AssetUploadNotFoundError, InvalidAssetUploadError
from backend.apps.assets.storage import ObjectMetadata, R2ObjectStorage
from backend.config.database import get_pool
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from PIL import Image

ADMIN_ID = UUID("40000000-0000-0000-0000-000000000001")
UPLOAD_ID = UUID("50000000-0000-0000-0000-000000000001")


class RecordingS3Client:
    def __init__(self, copy_error: ClientError | None = None) -> None:
        self.copy_error = copy_error
        self.presign_call: tuple[str, dict[str, Any], int] | None = None
        self.copy_call: dict[str, Any] | None = None
        self.deleted_keys: list[str] = []

    def generate_presigned_url(
        self,
        client_method: str,
        *,
        Params: dict[str, Any],
        ExpiresIn: int,
    ) -> str:
        self.presign_call = (client_method, Params, ExpiresIn)
        return "https://r2.example.test/presigned-put"

    def copy_object(self, **kwargs: Any) -> None:
        self.copy_call = kwargs
        if self.copy_error is not None:
            raise self.copy_error

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        assert Bucket == "assets"
        self.deleted_keys.append(Key)


def create_r2_storage(monkeypatch: Any, client: RecordingS3Client) -> R2ObjectStorage:
    monkeypatch.setattr(storage_module.boto3, "client", lambda **_kwargs: client)
    return R2ObjectStorage(
        endpoint_url="https://account.r2.cloudflarestorage.com",
        access_key_id="access-key",
        secret_access_key="secret-key",
        bucket_name="assets",
        public_base_url="https://assets.example.test",
    )


def test_r2_storage_extracts_only_canonical_public_object_keys(monkeypatch: Any) -> None:
    monkeypatch.setattr(storage_module.boto3, "client", lambda **_kwargs: object())
    storage = R2ObjectStorage(
        endpoint_url="https://account.r2.cloudflarestorage.com",
        access_key_id="access-key",
        secret_access_key="secret-key",
        bucket_name="assets",
        public_base_url="https://assets.example.test/cdn",
    )

    valid_url = "https://assets.example.test/cdn/products/images/image-id.jpg"
    assert storage.object_key_from_public_url(valid_url) == "products/images/image-id.jpg"
    assert storage.object_key_from_public_url(f"{valid_url}?version=1") is None
    assert storage.object_key_from_public_url(
        "https://assets.example.test/cdn/products/%2E%2E/private.jpg"
    ) is None
    assert storage.object_key_from_public_url(
        "https://assets.example.test/cdn-other/products/images/image-id.jpg"
    ) is None
    assert storage.object_key_from_public_url(
        "https://assets.example.test.evil/cdn/products/images/image-id.jpg"
    ) is None


def test_r2_upload_url_signs_the_declared_content_length(monkeypatch: Any) -> None:
    client = RecordingS3Client()
    storage = create_r2_storage(monkeypatch, client)

    upload_url = storage.create_upload_url(
        "pending/products/images/upload-id",
        "image/png",
        204_800,
        900,
    )

    assert upload_url == "https://r2.example.test/presigned-put"
    assert client.presign_call == (
        "put_object",
        {
            "Bucket": "assets",
            "Key": "pending/products/images/upload-id",
            "ContentType": "image/png",
            "ContentLength": 204_800,
        },
        900,
    )


def test_r2_promotion_is_conditional_on_the_validated_etag(monkeypatch: Any) -> None:
    client = RecordingS3Client()
    storage = create_r2_storage(monkeypatch, client)

    storage._promote_object(
        "pending/products/images/upload-id",
        "products/images/upload-id.png",
        "image/png",
        '"validated-etag"',
    )

    assert client.copy_call == {
        "Bucket": "assets",
        "Key": "products/images/upload-id.png",
        "CopySource": {
            "Bucket": "assets",
            "Key": "pending/products/images/upload-id",
        },
        "CopySourceIfMatch": '"validated-etag"',
        "ContentType": "image/png",
        "CacheControl": "public, max-age=31536000, immutable",
        "MetadataDirective": "REPLACE",
    }
    assert client.deleted_keys == ["pending/products/images/upload-id"]


def test_r2_promotion_treats_a_replaced_source_as_an_invalid_upload(monkeypatch: Any) -> None:
    precondition_error = ClientError(
        {
            "Error": {"Code": "PreconditionFailed", "Message": "ETag does not match"},
            "ResponseMetadata": {"HTTPStatusCode": 412},
        },
        "CopyObject",
    )
    client = RecordingS3Client(copy_error=precondition_error)
    storage = create_r2_storage(monkeypatch, client)

    with pytest.raises(InvalidAssetUploadError, match="changed during validation"):
        storage._promote_object(
            "pending/products/images/upload-id",
            "products/images/upload-id.png",
            "image/png",
            '"validated-etag"',
        )

    assert client.deleted_keys == []


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
        self.etag = '"test-etag"'
        self.created_upload: tuple[str, str, int, int] | None = None
        self.promoted: tuple[str, str, str, str] | None = None
        self.deleted: list[str] = []
        self.staging_exists = True
        self.final_exists = False
        self.replace_after_read = False
        self.promotion_attempted = False

    def create_upload_url(
        self,
        object_key: str,
        content_type: str,
        size_bytes: int,
        expires_in: int,
    ) -> str:
        self.created_upload = (object_key, content_type, size_bytes, expires_in)
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
            etag=self.etag,
        )

    async def read_object(self, object_key: str, etag: str, max_bytes: int) -> bytes:
        assert etag == self.etag
        assert max_bytes == 5 * 1024 * 1024
        data = self.data
        if self.replace_after_read and object_key.startswith("pending/"):
            self.data = b"replacement uploaded after validation"
            self.etag = '"replacement-etag"'
        return data

    async def promote_object(
        self,
        source_key: str,
        destination_key: str,
        content_type: str,
        source_etag: str,
    ) -> None:
        self.promotion_attempted = True
        if source_etag != self.etag:
            raise InvalidAssetUploadError("Uploaded asset changed during validation")
        self.promoted = (source_key, destination_key, content_type, source_etag)
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
    assert response.json()["headers"] == {
        "Content-Type": "image/png",
        "Content-Length": str(len(storage.data)),
    }
    assert datetime.fromisoformat(response.json()["expires_at"]) > before_request
    assert storage.created_upload == (
        f"pending/products/images/{UPLOAD_ID}",
        "image/png",
        len(storage.data),
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
        '"test-etag"',
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


def test_complete_product_image_rejects_replacement_after_validation(monkeypatch: Any) -> None:
    storage = FakeAssetStorage(png_bytes())
    storage.replace_after_read = True
    app = configure_test_app(monkeypatch, storage)

    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/admin/assets/uploads/{UPLOAD_ID}/complete",
                json={
                    "purpose": "product_image",
                    "content_type": "image/png",
                    "size_bytes": len(png_bytes()),
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json() == {"detail": "Uploaded asset changed during validation"}
    assert storage.promotion_attempted is True
    assert storage.promoted is None
    assert storage.final_exists is False
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
