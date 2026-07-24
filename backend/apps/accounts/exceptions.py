class AuthenticationError(Exception):
    def __init__(self, detail: str = "Authentication required") -> None:
        self.detail = detail
        super().__init__(detail)


class AuthorizationError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class AccountConflictError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class AccountProvisioningError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class AuthenticationServiceUnavailableError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class UserWriteConflictError(Exception):
    pass
