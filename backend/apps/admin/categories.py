"""Compatibility exports for category administration."""

from backend.apps.categories.admin_routers import router
from backend.apps.categories.admin_service import (
    create_category,
    delete_category,
    get_category,
    list_categories,
    update_category,
)
from backend.apps.categories.exceptions import (
    CategoryDeleteConflictError,
    CategoryHierarchyError,
    CategoryNotFoundError,
    DuplicateCategorySlugError,
    ParentCategoryNotFoundError,
)
from backend.apps.categories.repository import CATEGORY_COLUMNS
from backend.apps.categories.repository import category_from_record as _category_from_record
from backend.apps.categories.schemas import (
    CategoryCreate,
    CategoryListResponse,
    CategoryRead,
    CategorySlug,
    CategoryUpdate,
    LocalizedDescription,
    LocalizedName,
    SortOrder,
)
from backend.config.database import DbPool

__all__ = [
    "CATEGORY_COLUMNS",
    "CategoryCreate",
    "CategoryDeleteConflictError",
    "CategoryHierarchyError",
    "CategoryListResponse",
    "CategoryNotFoundError",
    "CategoryRead",
    "CategorySlug",
    "CategoryUpdate",
    "DbPool",
    "DuplicateCategorySlugError",
    "LocalizedDescription",
    "LocalizedName",
    "ParentCategoryNotFoundError",
    "SortOrder",
    "_category_from_record",
    "create_category",
    "delete_category",
    "get_category",
    "list_categories",
    "router",
    "update_category",
]
