from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from backend.apps.common.enums import CategoryStatus


class PublicCategoryRead(BaseModel):
    id: UUID
    parent_id: UUID | None
    slug: str
    name: str
    description: str | None
    status: CategoryStatus
    sort_order: int
    created_at: datetime
    updated_at: datetime
