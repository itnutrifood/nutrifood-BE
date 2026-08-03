from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MediaType = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=3,
        max_length=100,
        pattern=r"^[a-z0-9.+-]+/[a-z0-9.+-]+$",
    ),
]


class AssetPurpose(StrEnum):
    PRODUCT_IMAGE = "product_image"


class AssetUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: AssetPurpose
    content_type: MediaType
    size_bytes: int = Field(ge=1)


class AssetUploadCreated(BaseModel):
    upload_id: UUID
    purpose: AssetPurpose
    upload_url: str
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str]
    expires_at: datetime


class AssetUploadCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: AssetPurpose
    content_type: MediaType
    size_bytes: int = Field(ge=1)


class ImageAssetMetadata(BaseModel):
    type: Literal["image"] = "image"
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class AssetRead(BaseModel):
    id: UUID
    purpose: AssetPurpose
    object_key: str
    url: str
    content_type: MediaType
    size_bytes: int = Field(ge=1)
    metadata: ImageAssetMetadata
