from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PublicTestimonialRead(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    author_title: str
    photo_url: str | None
    review: str
    rating: int
    sort_order: int
    created_at: datetime
    updated_at: datetime
