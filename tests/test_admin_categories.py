import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from backend.apps.admin import auth as admin_auth_module
from backend.apps.categories import admin_service as category_admin_service
from backend.apps.categories import repository as category_repository
from backend.apps.categories.exceptions import CategoryHierarchyError
from backend.apps.categories.schemas import CategoryRead, CategoryUpdate
from backend.config.database import get_pool
from fastapi.testclient import TestClient

CATEGORY_ID = UUID("00000000-0000-0000-0000-000000000001")
PARENT_ID = UUID("00000000-0000-0000-0000-000000000002")
ADMIN_ID = UUID("40000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 1, 1, tzinfo=UTC)


class DummyPool:
    async def close(self) -> None:
        return None


async def create_dummy_pool() -> DummyPool:
    return DummyPool()


def category_record(
    *,
    category_id: UUID = CATEGORY_ID,
    parent_id: UUID | None = None,
    slug: str = "healthy-bowls",
    name: str | None = None,
    description: str | None = None,
    status: str = "active",
    sort_order: int = 10,
) -> dict[str, object]:
    return {
        "id": category_id,
        "parent_id": parent_id,
        "slug": slug,
        "name": name
        or json.dumps(
            {
                "HY-AM": "Healthy Bowls HY",
                "EN-US": "Healthy Bowls",
                "RU-RU": "Healthy Bowls RU",
            }
        ),
        "description": description or json.dumps({"EN-US": "Fresh meals"}),
        "status": status,
        "sort_order": sort_order,
        "created_at": NOW,
        "updated_at": NOW,
    }


class CreateCategoryPool:
    def __init__(self) -> None:
        self.insert_args: tuple[object, ...] | None = None

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "SELECT EXISTS" in query:
            return {"exists": True}

        if "INSERT INTO categories" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        self.insert_args = args
        return category_record(
            parent_id=args[0] if isinstance(args[0], UUID) else None,
            slug=str(args[1]),
            name=str(args[2]),
            description=str(args[3]),
            status=str(args[4]),
            sort_order=int(args[5]),
        )


class ListCategoryPool:
    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "SELECT count(*) AS total" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        assert args == ("active",)
        return {"total": 101}

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        if "FROM categories" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        assert args == ("active", 50, 50)
        return [category_record()]


class DeleteCategoryPool:
    def __init__(self) -> None:
        self.deleted_category_id: UUID | None = None

    async def execute(self, query: str, *args: object) -> str:
        if "DELETE FROM categories" not in query:
            raise AssertionError(f"Unexpected query: {query}")

        self.deleted_category_id = args[0] if isinstance(args[0], UUID) else None
        return "DELETE 1"


def configure_test_app(monkeypatch: Any, pool: object) -> Any:
    from backend.config import database
    from backend.config.asgi import app

    monkeypatch.setattr(database, "create_pool", create_dummy_pool)
    app.dependency_overrides[admin_auth_module.admin_auth] = lambda: admin_auth_module.AdminUser(
        id=ADMIN_ID,
        username="admin@mail.com",
        token_version=1,
    )
    app.dependency_overrides[get_pool] = lambda: pool
    return app


def test_admin_can_create_category(monkeypatch: Any) -> None:
    pool = CreateCategoryPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/categories",
                json={
                    "parent_id": str(PARENT_ID),
                    "slug": "healthy-bowls",
                    "name": {
                        "HY-AM": "Healthy Bowls HY",
                        "EN-US": "Healthy Bowls",
                        "RU-RU": "Healthy Bowls RU",
                    },
                    "description": {"EN-US": "Fresh meals"},
                    "status": "active",
                    "sort_order": 10,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["name"] == {
        "HY-AM": "Healthy Bowls HY",
        "EN-US": "Healthy Bowls",
        "RU-RU": "Healthy Bowls RU",
    }
    assert response.json()["description"] == {"EN-US": "Fresh meals"}
    assert pool.insert_args is not None
    assert json.loads(str(pool.insert_args[2])) == {
        "HY-AM": "Healthy Bowls HY",
        "EN-US": "Healthy Bowls",
        "RU-RU": "Healthy Bowls RU",
    }


def test_admin_can_list_active_categories(monkeypatch: Any) -> None:
    app = configure_test_app(monkeypatch, ListCategoryPool())

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/admin/categories?status=active&page=2&limit=50")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total"] == 101
    assert response.json()["page"] == 2
    assert response.json()["limit"] == 50
    assert response.json()["total_pages"] == 3
    assert "offset" not in response.json()
    assert response.json()["items"][0]["slug"] == "healthy-bowls"


def test_admin_delete_category_returns_no_content(monkeypatch: Any) -> None:
    pool = DeleteCategoryPool()
    app = configure_test_app(monkeypatch, pool)

    try:
        with TestClient(app) as client:
            response = client.delete(f"/api/v1/admin/categories/{CATEGORY_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert response.content == b""
    assert pool.deleted_category_id == CATEGORY_ID


class HierarchyConnectionContext:
    def __init__(self, pool: "HierarchyPool") -> None:
        self.connection = HierarchyConnection(pool)

    async def __aenter__(self) -> "HierarchyConnection":
        self.connection.pool.connections.append(self.connection)
        return self.connection

    async def __aexit__(self, *_args: object) -> None:
        return None


class HierarchyTransactionContext:
    def __init__(self, connection: "HierarchyConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "HierarchyConnection":
        assert not self.connection.in_transaction
        self.connection.in_transaction = True
        self.connection.pool.transaction_count += 1
        return self.connection

    async def __aexit__(self, *args: object) -> None:
        exception_type = args[0]
        self.connection.pool.transaction_outcomes.append(exception_type)
        if self.connection.holds_hierarchy_lock:
            self.connection.pool.hierarchy_lock.release()
            self.connection.holds_hierarchy_lock = False
        self.connection.in_transaction = False


class HierarchyConnection:
    def __init__(self, pool: "HierarchyPool") -> None:
        self.pool = pool
        self.in_transaction = False
        self.holds_hierarchy_lock = False

    def transaction(self) -> HierarchyTransactionContext:
        return HierarchyTransactionContext(self)

    async def fetchval(self, query: str, *args: object) -> None:
        assert self.in_transaction
        assert "pg_advisory_xact_lock" in query
        assert args == (category_repository.CATEGORY_HIERARCHY_LOCK_KEY,)
        if self.pool.hierarchy_lock.locked():
            self.pool.lock_wait_count += 1
        await self.pool.hierarchy_lock.acquire()
        self.holds_hierarchy_lock = True
        self.pool.lock_count += 1


class HierarchyPool:
    def __init__(self) -> None:
        self.hierarchy_lock = asyncio.Lock()
        self.connections: list[HierarchyConnection] = []
        self.transaction_outcomes: list[object] = []
        self.transaction_count = 0
        self.lock_count = 0
        self.lock_wait_count = 0

    def acquire(self) -> HierarchyConnectionContext:
        return HierarchyConnectionContext(self)


async def test_concurrent_parent_moves_are_serialized_and_rechecked(
    monkeypatch: Any,
) -> None:
    pool = HierarchyPool()
    parents: dict[UUID, UUID | None] = {
        CATEGORY_ID: None,
        PARENT_ID: None,
    }

    def assert_locked_connection(database: object) -> HierarchyConnection:
        assert isinstance(database, HierarchyConnection)
        assert database.in_transaction
        assert database.holds_hierarchy_lock
        return database

    async def fake_category_exists(database: object, category_id: UUID) -> bool:
        assert_locked_connection(database)
        await asyncio.sleep(0)
        return category_id in parents

    async def fake_is_descendant(
        database: object,
        category_id: UUID,
        parent_id: UUID,
    ) -> bool:
        assert_locked_connection(database)
        current_id: UUID | None = parent_id
        visited: set[UUID] = set()
        while current_id is not None and current_id not in visited:
            if current_id == category_id:
                return True
            visited.add(current_id)
            current_id = parents[current_id]
        return False

    async def fake_update_category(
        database: object,
        category_id: UUID,
        payload: CategoryUpdate,
    ) -> CategoryRead:
        assert_locked_connection(database)
        parents[category_id] = payload.parent_id
        return category_repository.category_from_record(
            category_record(category_id=category_id, parent_id=payload.parent_id)
        )

    monkeypatch.setattr(category_repository, "category_exists", fake_category_exists)
    monkeypatch.setattr(category_repository, "is_descendant", fake_is_descendant)
    monkeypatch.setattr(category_repository, "update_category", fake_update_category)

    results = await asyncio.gather(
        category_admin_service.update_category(
            pool,  # type: ignore[arg-type]
            CATEGORY_ID,
            CategoryUpdate(parent_id=PARENT_ID),
        ),
        category_admin_service.update_category(
            pool,  # type: ignore[arg-type]
            PARENT_ID,
            CategoryUpdate(parent_id=CATEGORY_ID),
        ),
        return_exceptions=True,
    )

    assert sum(isinstance(result, CategoryRead) for result in results) == 1
    assert sum(isinstance(result, CategoryHierarchyError) for result in results) == 1
    assert pool.transaction_count == 2
    assert pool.lock_count == 2
    assert pool.lock_wait_count == 1
    assert pool.transaction_outcomes.count(None) == 1
    assert pool.transaction_outcomes.count(CategoryHierarchyError) == 1
    assert all(connection.in_transaction is False for connection in pool.connections)
    assert all(connection.holds_hierarchy_lock is False for connection in pool.connections)

    for category_id in parents:
        current_id: UUID | None = category_id
        visited: set[UUID] = set()
        while current_id is not None:
            assert current_id not in visited
            visited.add(current_id)
            current_id = parents[current_id]


class DescendantQueryPool:
    def __init__(self) -> None:
        self.query: str | None = None
        self.args: tuple[object, ...] | None = None

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        self.query = query
        self.args = args
        return {"exists": False}


async def test_descendant_query_deduplicates_nodes_to_terminate_on_cycles() -> None:
    pool = DescendantQueryPool()

    is_descendant = await category_repository.is_descendant(  # type: ignore[arg-type]
        pool,
        CATEGORY_ID,
        PARENT_ID,
    )

    assert is_descendant is False
    assert pool.query is not None
    assert "WITH RECURSIVE descendants" in pool.query
    assert "UNION ALL" not in pool.query
    assert "UNION" in pool.query
    assert pool.args == (CATEGORY_ID, PARENT_ID)
