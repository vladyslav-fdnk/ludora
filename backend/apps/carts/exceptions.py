class CartError(Exception):
    status_code = 400


class EmptyCartError(CartError):
    pass


class ProductUnavailableError(CartError):
    pass


class CartConflictError(CartError):
    status_code = 409

