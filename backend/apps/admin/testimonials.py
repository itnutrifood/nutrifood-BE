"""Compatibility exports for testimonial administration."""

from backend.apps.testimonials.admin_routers import router
from backend.apps.testimonials.admin_service import (
    create_testimonial,
    delete_testimonial,
    get_testimonial,
    list_testimonials,
    update_testimonial,
)
from backend.apps.testimonials.exceptions import TestimonialNotFoundError
from backend.apps.testimonials.repository import TESTIMONIAL_COLUMNS
from backend.apps.testimonials.repository import (
    testimonial_from_record as _testimonial_from_record,
)
from backend.apps.testimonials.schemas import (
    AuthorTitle,
    PersonName,
    PhotoUrl,
    Rating,
    Review,
    SortOrder,
    TestimonialCreate,
    TestimonialListResponse,
    TestimonialRead,
    TestimonialUpdate,
)
from backend.config.database import DbPool

__all__ = [
    "AuthorTitle",
    "DbPool",
    "PersonName",
    "PhotoUrl",
    "Rating",
    "Review",
    "SortOrder",
    "TESTIMONIAL_COLUMNS",
    "TestimonialCreate",
    "TestimonialListResponse",
    "TestimonialNotFoundError",
    "TestimonialRead",
    "TestimonialUpdate",
    "_testimonial_from_record",
    "create_testimonial",
    "delete_testimonial",
    "get_testimonial",
    "list_testimonials",
    "router",
    "update_testimonial",
]
