class AdminAuthenticationError(Exception):
    def __init__(self, detail: str = "Admin authentication required") -> None:
        self.detail = detail
        super().__init__(detail)


class AdminAuthNotConfiguredError(Exception):
    pass
