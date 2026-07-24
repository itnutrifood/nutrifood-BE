"""Compatibility exports for product administration."""

from backend.apps.products.admin_routers import router
from backend.apps.products.admin_service import (
    create_product,
    delete_product,
    get_product,
    list_products,
    update_product,
)
from backend.apps.products.exceptions import (
    DuplicateProductSlugError,
    ProductCategoryNotFoundError,
    ProductNotFoundError,
)
from backend.apps.products.repository import PRODUCT_COLUMNS
from backend.apps.products.repository import product_from_record as _product_from_record
from backend.apps.products.schemas import (
    MAX_PRODUCT_IMAGES,
    ImageDimension,
    ImageSizeBytes,
    ImageUrl,
    LocalizedText,
    LocalizedTextValue,
    LocalizedWord,
    LocalizedWords,
    OptionalLocalizedText,
    ProductCreate,
    ProductImage,
    ProductListResponse,
    ProductPrice,
    ProductRead,
    ProductSlug,
    ProductUpdate,
    ReadinessTimeMinutes,
)
from backend.config.database import DbPool

__all__ = [
    "DbPool",
    "ImageDimension",
    "ImageSizeBytes",
    "ImageUrl",
    "PRODUCT_COLUMNS",
    "DuplicateProductSlugError",
    "LocalizedText",
    "LocalizedTextValue",
    "LocalizedWord",
    "LocalizedWords",
    "MAX_PRODUCT_IMAGES",
    "OptionalLocalizedText",
    "ProductCategoryNotFoundError",
    "ProductCreate",
    "ProductImage",
    "ProductListResponse",
    "ProductNotFoundError",
    "ProductPrice",
    "ProductRead",
    "ProductSlug",
    "ProductUpdate",
    "ReadinessTimeMinutes",
    "_product_from_record",
    "create_product",
    "delete_product",
    "get_product",
    "list_products",
    "router",
    "update_product",
]
