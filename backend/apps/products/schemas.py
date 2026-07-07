from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from backend.apps.admin.products import ProductImage


class PublicProductRead(BaseModel):
    id: UUID
    slug: str | None
    title: str
    description: str
    images: list[ProductImage]
    category_ids: list[UUID]
    image_tags: list[str]
    text_tags: list[str]
    serving_size: str | None
    readiness_time_minutes: int | None
    price: Decimal
    allergens: list[str]
    allergen_information: str | None
    storage_delivery: str | None
    created_at: datetime
    updated_at: datetime
