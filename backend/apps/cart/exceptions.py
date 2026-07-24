from collections.abc import Sequence
from uuid import UUID


class CartProductNotFoundError(Exception):
    def __init__(self, product_ids: Sequence[UUID]) -> None:
        self.product_ids = list(product_ids)
        super().__init__("One or more products were not found")
