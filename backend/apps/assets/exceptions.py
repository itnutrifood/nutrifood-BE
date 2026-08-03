class AssetStorageNotConfiguredError(Exception):
    pass


class AssetStorageUnavailableError(Exception):
    pass


class AssetUploadNotFoundError(Exception):
    pass


class InvalidAssetUploadError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)
