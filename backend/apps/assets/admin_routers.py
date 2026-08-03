from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi import status as http_status

from backend.apps.assets.dependencies import AssetStorage
from backend.apps.assets.schemas import (
    AssetRead,
    AssetUploadCompletion,
    AssetUploadCreated,
    AssetUploadRequest,
)
from backend.apps.assets.service import complete_asset_upload, create_asset_upload
from backend.config.settings import Settings, get_settings

router = APIRouter(prefix="/assets", tags=["admin:assets"])


@router.post(
    "/uploads",
    response_model=AssetUploadCreated,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_admin_asset_upload(
    payload: AssetUploadRequest,
    storage: AssetStorage,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssetUploadCreated:
    return await create_asset_upload(
        storage,
        payload,
        settings.r2_upload_url_expire_seconds,
    )


@router.post("/uploads/{upload_id}/complete", response_model=AssetRead)
async def complete_admin_asset_upload(
    upload_id: UUID,
    payload: AssetUploadCompletion,
    storage: AssetStorage,
) -> AssetRead:
    return await complete_asset_upload(storage, upload_id, payload)
