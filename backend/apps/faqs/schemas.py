from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PublicFAQRead(BaseModel):
    id: UUID
    slug: str
    question: str
    answer: str
    sort_order: int
    created_at: datetime
    updated_at: datetime
