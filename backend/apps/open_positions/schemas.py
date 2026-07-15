from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from backend.apps.common.enums import EmploymentType


class PublicOpenPositionRead(BaseModel):
    id: UUID
    title: str
    employment_type: EmploymentType
    description: str
    position: str
    city: str
    created_at: datetime
    updated_at: datetime
