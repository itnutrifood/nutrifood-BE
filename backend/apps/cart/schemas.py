from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from backend.apps.products.schemas import PublicProductRead

MAX_CART_ITEM_QUANTITY = 99
MAX_CART_ITEMS = 100


class CartItemUpsert(BaseModel):
    quantity: int = Field(ge=1, le=MAX_CART_ITEM_QUANTITY)


class CartItemBatchUpsert(CartItemUpsert):
    product_id: UUID


class CartItemsUpsert(BaseModel):
    items: list[CartItemBatchUpsert] = Field(min_length=1, max_length=MAX_CART_ITEMS)

    @model_validator(mode="after")
    def product_ids_are_unique(self) -> Self:
        product_ids = [item.product_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Cart product IDs must be unique")
        return self


class CartItemRead(BaseModel):
    product: PublicProductRead
    quantity: int
    line_total: Decimal


class CartRead(BaseModel):
    items: list[CartItemRead]
    total_quantity: int
    subtotal: Decimal
