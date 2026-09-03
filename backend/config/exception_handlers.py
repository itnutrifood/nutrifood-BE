from collections.abc import Sequence
from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from backend.apps.accounts.exceptions import (
    AccountConflictError,
    AccountProvisioningError,
    AuthenticationError,
    AuthenticationServiceUnavailableError,
    AuthorizationError,
)
from backend.apps.admin.auth_exceptions import (
    AdminAuthenticationError,
    AdminAuthNotConfiguredError,
)
from backend.apps.assets.exceptions import (
    AssetStorageNotConfiguredError,
    AssetStorageUnavailableError,
    AssetUploadNotFoundError,
    InvalidAssetUploadError,
)
from backend.apps.cart.exceptions import CartProductNotFoundError
from backend.apps.categories.exceptions import (
    CategoryDeleteConflictError,
    CategoryFilterConflictError,
    CategoryHierarchyError,
    CategoryNotFoundError,
    DuplicateCategorySlugError,
    ParentCategoryNotFoundError,
)
from backend.apps.checkout.exceptions import (
    CheckoutAddressNotFoundError,
    EmptyCartError,
    IdempotencyConflictError,
)
from backend.apps.common.exceptions import InvalidCursorError
from backend.apps.contacts.exceptions import ContactMessageNotFoundError
from backend.apps.faqs.exceptions import DuplicateFAQSlugError, FAQNotFoundError
from backend.apps.favorites.exceptions import FavoriteProductNotFoundError
from backend.apps.notifications.exceptions import FcmRegistrationNotFoundError
from backend.apps.open_positions.exceptions import OpenPositionNotFoundError
from backend.apps.orders.exceptions import OrderNotFoundError
from backend.apps.products.exceptions import (
    DuplicateProductSlugError,
    ProductCategoryNotFoundError,
    ProductNotFoundError,
)
from backend.apps.subscriptions.exceptions import (
    DuplicateSubscriptionPlanSlugError,
    SubscriptionPlanNotFoundError,
)
from backend.apps.testimonials.exceptions import TestimonialNotFoundError
from backend.apps.users.addresses.exceptions import (
    AddressGeocodingNotConfiguredError,
    AddressGeocodingUnavailableError,
    AddressNotFoundError,
    InvalidAddressLocationError,
)

DOMAIN_EXCEPTION_TYPES: tuple[type[Exception], ...] = (
    AuthenticationError,
    AuthorizationError,
    AccountConflictError,
    AccountProvisioningError,
    AuthenticationServiceUnavailableError,
    AdminAuthenticationError,
    AdminAuthNotConfiguredError,
    InvalidCursorError,
    CategoryNotFoundError,
    ParentCategoryNotFoundError,
    DuplicateCategorySlugError,
    CategoryHierarchyError,
    CategoryDeleteConflictError,
    CategoryFilterConflictError,
    FAQNotFoundError,
    DuplicateFAQSlugError,
    OpenPositionNotFoundError,
    ProductNotFoundError,
    ProductCategoryNotFoundError,
    DuplicateProductSlugError,
    SubscriptionPlanNotFoundError,
    DuplicateSubscriptionPlanSlugError,
    TestimonialNotFoundError,
    ContactMessageNotFoundError,
    CartProductNotFoundError,
    CheckoutAddressNotFoundError,
    EmptyCartError,
    IdempotencyConflictError,
    FavoriteProductNotFoundError,
    FcmRegistrationNotFoundError,
    AddressNotFoundError,
    AddressGeocodingNotConfiguredError,
    AddressGeocodingUnavailableError,
    InvalidAddressLocationError,
    OrderNotFoundError,
    AssetStorageNotConfiguredError,
    AssetStorageUnavailableError,
    AssetUploadNotFoundError,
    InvalidAssetUploadError,
)


def _not_found(detail: str) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": detail})


def _conflict(detail: str) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": detail})


async def domain_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, AuthenticationError):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": exc.detail},
            headers={"WWW-Authenticate": "Bearer"},
        )
    if isinstance(exc, AuthorizationError):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": exc.detail},
        )
    if isinstance(exc, AccountConflictError):
        return _conflict(exc.detail)
    if isinstance(exc, AccountProvisioningError):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": exc.detail},
        )
    if isinstance(exc, AuthenticationServiceUnavailableError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": exc.detail},
        )
    if isinstance(exc, AdminAuthenticationError):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": exc.detail},
            headers={"WWW-Authenticate": "Bearer"},
        )
    if isinstance(exc, AdminAuthNotConfiguredError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Admin authentication is not configured"},
        )
    if isinstance(exc, InvalidCursorError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": "Invalid cursor"},
        )
    if isinstance(exc, CategoryFilterConflictError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": str(exc)},
        )
    if isinstance(exc, CategoryNotFoundError):
        return _not_found("Category not found")
    if isinstance(exc, ParentCategoryNotFoundError):
        return _not_found("Parent category not found")
    if isinstance(exc, DuplicateCategorySlugError):
        return _conflict("Category slug already exists")
    if isinstance(exc, CategoryHierarchyError):
        return _conflict(str(exc))
    if isinstance(exc, CategoryDeleteConflictError):
        return _conflict("Category has child categories or linked records")
    if isinstance(exc, FAQNotFoundError):
        return _not_found("FAQ not found")
    if isinstance(exc, DuplicateFAQSlugError):
        return _conflict("FAQ slug already exists")
    if isinstance(exc, OpenPositionNotFoundError):
        return _not_found("Open position not found")
    if isinstance(exc, ProductNotFoundError):
        return _not_found("Product not found")
    if isinstance(exc, ProductCategoryNotFoundError):
        return _not_found("Product category not found")
    if isinstance(exc, DuplicateProductSlugError):
        return _conflict("Product slug already exists")
    if isinstance(exc, SubscriptionPlanNotFoundError):
        return _not_found("Subscription plan not found")
    if isinstance(exc, DuplicateSubscriptionPlanSlugError):
        return _conflict("Subscription plan slug already exists")
    if isinstance(exc, TestimonialNotFoundError):
        return _not_found("Testimonial not found")
    if isinstance(exc, ContactMessageNotFoundError):
        return _not_found("Contact message not found")
    if isinstance(exc, CartProductNotFoundError | FavoriteProductNotFoundError):
        product_ids = cast(Sequence[object], exc.product_ids)
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "detail": {
                    "message": "One or more products were not found",
                    "product_ids": [str(product_id) for product_id in product_ids],
                }
            },
        )
    if isinstance(exc, CheckoutAddressNotFoundError):
        return _not_found("Delivery address not found")
    if isinstance(exc, EmptyCartError):
        return _conflict("Cannot place an order with an empty cart")
    if isinstance(exc, IdempotencyConflictError):
        return _conflict("Idempotency key was already used with a different request")
    if isinstance(exc, FcmRegistrationNotFoundError):
        return _not_found("No FCM registration found for the current user")
    if isinstance(exc, AddressNotFoundError):
        return _not_found("Address not found")
    if isinstance(exc, AddressGeocodingNotConfiguredError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Address lookup is not configured"},
        )
    if isinstance(exc, AddressGeocodingUnavailableError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Address lookup is temporarily unavailable"},
        )
    if isinstance(exc, InvalidAddressLocationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": exc.detail},
        )
    if isinstance(exc, OrderNotFoundError):
        return _not_found("Order not found")
    if isinstance(exc, AssetStorageNotConfiguredError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Asset storage is not configured"},
        )
    if isinstance(exc, AssetStorageUnavailableError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Asset storage is temporarily unavailable"},
        )
    if isinstance(exc, AssetUploadNotFoundError):
        return _not_found("Asset upload not found")
    if isinstance(exc, InvalidAssetUploadError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": exc.detail},
        )

    raise exc


def register_exception_handlers(app: FastAPI) -> None:
    for exception_type in DOMAIN_EXCEPTION_TYPES:
        app.add_exception_handler(exception_type, domain_exception_handler)
