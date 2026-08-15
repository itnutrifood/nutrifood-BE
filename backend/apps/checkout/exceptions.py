class CheckoutAddressNotFoundError(Exception):
    pass


class EmptyCartError(Exception):
    pass


class IdempotencyConflictError(Exception):
    pass
