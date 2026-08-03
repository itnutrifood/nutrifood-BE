from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from backend.apps.assets.storage import AssetObjectStorage, R2ObjectStorage
from backend.config.settings import Settings, get_settings


@lru_cache
def _create_asset_storage(
    endpoint_url: str,
    access_key_id: str,
    secret_access_key: str,
    bucket_name: str,
    public_base_url: str,
) -> AssetObjectStorage:
    return R2ObjectStorage(
        endpoint_url=endpoint_url,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        bucket_name=bucket_name,
        public_base_url=public_base_url,
    )


def get_asset_storage(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssetObjectStorage:
    return _create_asset_storage(
        settings.r2_endpoint_url,
        settings.r2_access_key_id,
        settings.r2_secret_access_key,
        settings.r2_bucket_name,
        settings.r2_public_base_url,
    )


AssetStorage = Annotated[
    AssetObjectStorage,
    Depends(get_asset_storage),
]
