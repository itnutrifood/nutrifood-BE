from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

from backend.apps.common.enums import OrderStatus, PaymentMethod, PaymentStatus
from backend.apps.common.pagination import Page
from backend.apps.products.schemas import LocalizedText
from backend.apps.users.addresses.enums import ArmeniaRegion, Country

ContactPhone = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=9,
        max_length=16,
        pattern=r"^\+[1-9][0-9]{7,14}$",
    ),
]
DeliveryNotes = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
OrderNumber = Annotated[
    str,
    StringConstraints(pattern=r"^NF[23456789A-HJ-NP-Z]{9}$"),
]


class PlaceOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address_id: UUID
    payment_method: PaymentMethod
    contact_phone: ContactPhone
    delivery_notes: DeliveryNotes | None = None


class DeliveryAddressSnapshot(BaseModel):
    country: Country
    region: ArmeniaRegion
    city: str
    street: str
    building_number: str
    entrance: str | None
    floor: str | None


class OrderItemRead(BaseModel):
    id: UUID
    product_id: UUID | None
    product_slug: str | None
    product_title: LocalizedText
    unit_price: Decimal
    quantity: int
    line_total: Decimal


class OrderSummaryRead(BaseModel):
    id: UUID
    order_number: OrderNumber
    user_id: UUID
    status: OrderStatus
    payment_method: PaymentMethod
    payment_status: PaymentStatus
    subtotal: Decimal
    delivery_fee: Decimal
    total: Decimal
    currency: str
    customer_first_name: str | None
    customer_last_name: str | None
    customer_email: str
    contact_phone: str
    created_at: datetime
    updated_at: datetime


class OrderRead(OrderSummaryRead):
    delivery_address: DeliveryAddressSnapshot
    delivery_notes: str | None
    items: list[OrderItemRead]


class OrderListResponse(Page[OrderSummaryRead]):
    pass
