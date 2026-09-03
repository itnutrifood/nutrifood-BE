class AddressNotFoundError(Exception):
    pass


class AddressGeocodingNotConfiguredError(Exception):
    pass


class AddressGeocodingUnavailableError(Exception):
    pass


class InvalidAddressLocationError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)
