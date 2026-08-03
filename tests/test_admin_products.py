import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from backend.apps.admin import auth as admin_auth_module
from backend.apps.assets.dependencies import get_asset_storage
from backend.config.database import get_pool
from fastapi.testclient import TestClient

PRODUCT_ID = UUID("10000000-0000-0000-0000-000000000001")
CATEGORY_ID = UUID("20000000-0000-0000-0000-000000000001")
ADMIN_ID = UUID("40000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 1, 1, tzinfo=UTC)
ASSET_BASE_URL = "https://assets.example.test"
EXISTING_ASSET_ID = UUID("50000000-0000-0000-0000-000000000001")
REMOVED_ASSET_ID = UUID("50000000-0000-0000-0000-000000000002")
RETAINED_ASSET_ID = UUID("50000000-0000-0000-0000-000000000003")
NEW_ASSET_ID = UUID("50000000-0000-0000-0000-000000000004")
EXISTING_IMAGE_URL = f"{ASSET_BASE_URL}/products/images/{EXISTING_ASSET_ID}.jpg"


class DummyPool:
    async def close(self) -> None:
        return None


async def create_dummy_pool() -> DummyPool:
    return DummyPool()


class FakeProductAssetStorage:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def object_key_from_public_url(self, url: str) -> str | None:
        prefix = f"{ASSET_BASE_URL}/"
        return url.removeprefix(prefix) if url.startswith(prefix) else None

    async def delete_object(self, object_key: str) -> None:
        self.deleted.append(object_key)


def localized_text(en_us: str) -> dict[str, str]:
    return {
        "HY-AM": f"{en_us} HY",
        "EN-US": en_us,
        "RU-RU": f"{en_us} RU",
    }


def localized_words(en_us: str) -> dict[str, list[str]]:
    return {
        "HY-AM": [f"{en_us} HY"],
        "EN-US": [en_us],
        "RU-RU": [f"{en_us} RU"],
    }


def product_payload() -> dict[str, object]:
    return {
        "slug": "mediterranean-bowl",
        "title": localized_text("Mediterranean Bowl"),
        "description": localized_text("Fresh bowl"),
        "images": [
            {
                "url": "https://cdn.example.test/mediterranean-bowl.jpg",
                "width": 1200,
                "height": 900,
                "size_bytes": 450_000,
            }
        ],
        "category_ids": [str(CATEGORY_ID)],
        "image_tags": localized_words("High Protein"),
        "text_tags": localized_words("bowls"),
        "serving_size": {"EN-US": "400g (1 serving)"},
        "readiness_time_minutes": 3,
        "price": "12.99",
        "allergens": localized_words("Sesame"),
        "allergen_information": {"EN-US": "Contains Sesame."},
        "storage_delivery": {"EN-US": "Keep refrigerated."},
    }


def product_record(
    *,
    product_id: UUID = PRODUCT_ID,
    slug: str | None = "mediterranean-bowl",
    title: str | None = None,
    description: str | None = None,
    images: str | None = None,
    image_tags: str | None = None,
    text_tags: str | None = None,
    serving_size: str | None = None,
    readiness_time_minutes: int | None = 3,
    price: Decimal = Decimal("12.99"),
    allergens: str | None = None,
    allergen_information: str | None = None,
    storage_delivery: str | None = None,
    category_ids: list[UUID] | None = None,
) -> dict[str, object]:
    return {
        "id": product_id,
        "slug": slug,
        "title": title or json.dumps(localized_text("Mediterranean Bowl")),
        "description": description or json.dumps(localized_text("Fresh bowl")),
        "images": images
        or json.dumps(
            [
                {
                    "url": "https://cdn.example.test/mediterranean-bowl.jpg",
                    "width": 1200,
                    "height": 900,
                    "size_bytes": 450_000,
                }
            ]
        ),
        "image_tags": image_tags or json.dumps(localized_words("High Protein")),
        "text_tags": text_tags or json.dumps(localized_words("bowls")),
        "serving_size": serving_size or json.dumps({"EN-US": "400g (1 serving)"}),
        "readiness_time_minutes": readiness_time_minutes,
        "price": price,
        "allergens": allergens or json.dumps(localized_words("Sesame")),
        "allergen_information": allergen_information or json.dumps({"EN-US": "Contains Sesame."}),
        "storage_delivery": storage_delivery or json.dumps({"EN-US": "Keep refrigerated."}),
        "created_at": NOW,
        "updated_at": NOW,
        "category_ids": category_ids or [CATEGORY_ID],
    }


class CreateProductPool:
    def __init__(self) -> None:
        self.insert_args: tuple[object, ...] | None = None

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        if "SELECT id FROM categories" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        assert args == ([CATEGORY_ID],)
        return [{"id": CATEGORY_ID}]

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "INSERT INTO products" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        self.insert_args = args
        return product_record(
            slug=args[0] if isinstance(args[0], str) else None,
            title=str(args[1]),
            description=str(args[2]),
            images=str(args[3]),
            image_tags=str(args[4]),
            text_tags=str(args[5]),
            serving_size=str(args[6]),
            readiness_time_minutes=args[7] if isinstance(args[7], int) else None,
            price=args[8] if isinstance(args[8], Decimal) else Decimal(str(args[8])),
            allergens=str(args[9]),
            allergen_information=str(args[10]),
            storage_delivery=str(args[11]),
        )


class ListProductPool:
    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "SELECT count(*) AS total" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        assert args == (CATEGORY_ID,)
        return {"total": 101}

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        if "FROM products AS p" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        assert args == (CATEGORY_ID, 50, 50)
        return [product_record()]


class UpdateProductPool:
    def __init__(self, old_images: list[dict[str, int | str]] | None = None) -> None:
        self.update_args: tuple[object, ...] | None = None
        self.old_images = old_images

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "UPDATE products" in query:
            self.update_args = args
            if "images =" in query:
                return product_record(images=str(args[1]))

            price = args[1] if isinstance(args[1], Decimal) else Decimal(str(args[1]))
            return product_record(price=price)
        if "FROM products AS p" in query:
            images = json.dumps(self.old_images) if self.old_images is not None else None
            return product_record(images=images)

        raise AssertionError(f"Unexpected query: {query}")


class DeleteProductPool:
    def __init__(self, images: list[dict[str, int | str]] | None = None) -> None:
        self.deleted_product_id: UUID | None = None
        self.images = images

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "FROM products AS p" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        images = json.dumps(self.images) if self.images is not None else None
        return product_record(images=images)

    async def execute(self, query: str, *args: object) -> str:
        if "DELETE FROM products" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        self.deleted_product_id = args[0] if isinstance(args[0], UUID) else None
        return "DELETE 1"


def configure_test_app(
    monkeypatch: Any,
    pool: object,
    storage: FakeProductAssetStorage | None = None,
) -> Any:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    app.dependency_overrides[admin_auth_module.admin_auth] = lambda: admin_auth_module.AdminUser(
        id=ADMIN_ID,
        username="admin@mail.com",
        token_version=1,
    )
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_asset_storage] = lambda: storage or FakeProductAssetStorage()
    return app


def test_admin_can_create_product(monkeypatch: Any) -> None:
    pool = CreateProductPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/admin/products", json=product_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["slug"] == "mediterranean-bowl"
    assert response.json()["category_ids"] == [str(CATEGORY_ID)]
    assert pool.insert_args is not None
    assert json.loads(str(pool.insert_args[3])) == [
        {
            "url": "https://cdn.example.test/mediterranean-bowl.jpg",
            "width": 1200,
            "height": 900,
            "size_bytes": 450_000,
        }
    ]
    assert json.loads(str(pool.insert_args[4])) == localized_words("High Protein")


def test_admin_can_list_products_by_category(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, ListProductPool())

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/admin/products?category_id={CATEGORY_ID}&page=2&limit=50"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total"] == 101
    assert response.json()["page"] == 2
    assert response.json()["limit"] == 50
    assert response.json()["total_pages"] == 3
    assert "offset" not in response.json()
    assert response.json()["items"][0]["slug"] == "mediterranean-bowl"


def test_admin_can_update_product(monkeypatch: Any) -> None:
    pool = UpdateProductPool()
    storage = FakeProductAssetStorage()
    app = configure_test_app(monkeypatch, pool, storage)

    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/admin/products/{PRODUCT_ID}",
                json={"price": "10.99"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert pool.update_args == (PRODUCT_ID, Decimal("10.99"))
    assert storage.deleted == []


def test_admin_update_product_deletes_only_removed_managed_images(monkeypatch: Any) -> None:
    removed_url = f"{ASSET_BASE_URL}/products/images/{REMOVED_ASSET_ID}.jpg"
    retained_url = f"{ASSET_BASE_URL}/products/images/{RETAINED_ASSET_ID}.webp"
    external_url = "https://legacy.example.test/external.jpg"
    old_images = [
        {"url": removed_url},
        {"url": retained_url},
        {"url": external_url},
        {"url": f"{ASSET_BASE_URL}/other/file.jpg"},
        {"url": f"{ASSET_BASE_URL}/products/images/not-managed.jpg"},
    ]
    new_images = [
        {"url": retained_url},
        {"url": f"{ASSET_BASE_URL}/products/images/{NEW_ASSET_ID}.png"},
    ]
    pool = UpdateProductPool(old_images)
    storage = FakeProductAssetStorage()
    app = configure_test_app(monkeypatch, pool, storage)

    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/admin/products/{PRODUCT_ID}",
                json={"images": new_images},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [image["url"] for image in response.json()["images"]] == [
        retained_url,
        new_images[1]["url"],
    ]
    assert storage.deleted == [f"products/images/{REMOVED_ASSET_ID}.jpg"]


def test_admin_delete_product_returns_no_content(monkeypatch: Any) -> None:
    images = [
        {"url": EXISTING_IMAGE_URL},
        {"url": "https://legacy.example.test/external.jpg"},
    ]
    pool = DeleteProductPool(images)
    storage = FakeProductAssetStorage()
    app = configure_test_app(monkeypatch, pool, storage)

    try:
        with TestClient(app) as client:
            response = client.delete(f"/api/v1/admin/products/{PRODUCT_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert pool.deleted_product_id == PRODUCT_ID
    assert storage.deleted == [f"products/images/{EXISTING_ASSET_ID}.jpg"]


def test_admin_product_rejects_oversized_image(monkeypatch: Any) -> None:
    payload = product_payload()
    payload["images"] = [
        {
            "url": "https://cdn.example.test/too-large.jpg",
            "width": 1200,
            "height": 900,
            "size_bytes": 5 * 1024 * 1024 + 1,
        }
    ]
    app = configure_test_app(monkeypatch, CreateProductPool())

    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/admin/products", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
