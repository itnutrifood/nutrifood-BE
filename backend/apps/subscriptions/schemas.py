from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from backend.apps.common.enums import SubscriptionPlanStatus


class PublicSubscriptionPlanRead(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str | None
    price: Decimal
    billing_interval: str
    meal_count_label: str | None
    is_popular: bool
    status: SubscriptionPlanStatus
    sort_order: int
    additional_info: list[str]
    created_at: datetime
    updated_at: datetime
