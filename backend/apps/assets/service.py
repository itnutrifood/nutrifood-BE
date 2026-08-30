import asyncio
import warnings
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from io import BytesIO
from uuid import UUID, uuid4

from PIL import Image, UnidentifiedImageError

from backend.apps.assets.exceptions import (
    AssetStorageUnavailableError,
    AssetUploadNotFoundError,
    InvalidAssetUploadError,
)
from backend.apps.assets.schemas import (
    AssetPurpose,
    AssetRead,
    AssetUploadCompletion,
    AssetUploadCreated,
    AssetUploadRequest,
    ImageAssetMetadata,
)
from backend.apps.assets.storage import AssetObjectStorage, ObjectMetadata
from backend.apps.products.schemas import (
    MAX_PRODUCT_IMAGE_DIMENSION,
    MAX_PRODUCT_IMAGE_SIZE_BYTES,
)


class AssetValidator(StrEnum):
    IMAGE = "image"


@dataclass(frozen=True)
class AssetUploadPolicy:
    pending_prefix: str
    public_prefix: str
    content_type_extensions: Mapping[str, str]
    max_size_bytes: int
    validator: AssetValidator
    max_image_dimension: int | None = None


ASSET_UPLOAD_POLICIES: dict[AssetPurpose, AssetUploadPolicy] = {
    AssetPurpose.PRODUCT_IMAGE: AssetUploadPolicy(
        pending_prefix="pending/products/images",
        public_prefix="products/images",
        content_type_extensions={
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        },
        max_size_bytes=MAX_PRODUCT_IMAGE_SIZE_BYTES,
        validator=AssetValidator.IMAGE,
        max_image_dimension=MAX_PRODUCT_IMAGE_DIMENSION,
    )
}
PILLOW_FORMAT_MEDIA_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def _policy_for(purpose: AssetPurpose) -> AssetUploadPolicy:
    return ASSET_UPLOAD_POLICIES[purpose]


def _validate_descriptor(
    policy: AssetUploadPolicy,
    content_type: str,
    size_bytes: int,
) -> None:
    if content_type not in policy.content_type_extensions:
        raise InvalidAssetUploadError("Content type is not allowed for this asset purpose")
    if size_bytes > policy.max_size_bytes:
        raise InvalidAssetUploadError(
            f"Asset exceeds the {policy.max_size_bytes // (1024 * 1024)} MiB limit"
        )


def _staging_key(policy: AssetUploadPolicy, upload_id: UUID) -> str:
    return f"{policy.pending_prefix}/{upload_id}"


def _final_key(
    policy: AssetUploadPolicy,
    upload_id: UUID,
    content_type: str,
) -> str:
    extension = policy.content_type_extensions[content_type]
    return f"{policy.public_prefix}/{upload_id}.{extension}"


async def create_asset_upload(
    storage: AssetObjectStorage,
    payload: AssetUploadRequest,
    expires_in: int,
) -> AssetUploadCreated:
    policy = _policy_for(payload.purpose)
    _validate_descriptor(policy, payload.content_type, payload.size_bytes)
    upload_id = uuid4()
    upload_url = storage.create_upload_url(
        _staging_key(policy, upload_id),
        payload.content_type,
        payload.size_bytes,
        expires_in,
    )
    return AssetUploadCreated(
        upload_id=upload_id,
        purpose=payload.purpose,
        upload_url=upload_url,
        headers={
            "Content-Type": payload.content_type,
            "Content-Length": str(payload.size_bytes),
        },
        expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
    )


def _validate_object_metadata(
    policy: AssetUploadPolicy,
    metadata: ObjectMetadata,
    payload: AssetUploadCompletion,
) -> None:
    if metadata.content_type != payload.content_type:
        raise InvalidAssetUploadError("Uploaded asset content type does not match the request")
    if metadata.size_bytes != payload.size_bytes:
        raise InvalidAssetUploadError("Uploaded asset size does not match the request")
    if metadata.size_bytes > policy.max_size_bytes:
        raise InvalidAssetUploadError(
            f"Uploaded asset exceeds the {policy.max_size_bytes // (1024 * 1024)} MiB limit"
        )


def _validate_product_image_bytes(
    data: bytes,
    expected_content_type: str,
    max_dimension: int,
) -> ImageAssetMetadata:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                width, height = image.size
                detected_content_type = PILLOW_FORMAT_MEDIA_TYPES.get(image.format or "")
                if detected_content_type != expected_content_type:
                    raise InvalidAssetUploadError(
                        "Uploaded file contents do not match its content type"
                    )
                if width > max_dimension or height > max_dimension:
                    raise InvalidAssetUploadError(
                        f"Asset image dimensions cannot exceed {max_dimension}px"
                    )
                image.verify()
    except InvalidAssetUploadError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise InvalidAssetUploadError("Asset image dimensions are too large") from exc
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise InvalidAssetUploadError("Uploaded file is not a valid image") from exc

    return ImageAssetMetadata(width=width, height=height)


async def _delete_invalid_upload(storage: AssetObjectStorage, object_key: str) -> None:
    try:
        await storage.delete_object(object_key)
    except AssetStorageUnavailableError:
        # A bucket lifecycle rule removes abandoned pending uploads as a backstop.
        pass


async def delete_product_image_urls(
    storage: AssetObjectStorage,
    urls: Iterable[str],
) -> None:
    # TODO: Enqueue deletions for durable Celery retries once worker infrastructure exists.
    policy = ASSET_UPLOAD_POLICIES[AssetPurpose.PRODUCT_IMAGE]
    public_prefix = f"{policy.public_prefix}/"
    allowed_extensions = frozenset(policy.content_type_extensions.values())
    object_keys = {
        object_key
        for url in urls
        if (object_key := storage.object_key_from_public_url(url)) is not None
        and object_key.startswith(public_prefix)
        and _is_managed_product_image_key(object_key, public_prefix, allowed_extensions)
    }
    await asyncio.gather(*(storage.delete_object(object_key) for object_key in object_keys))


def _is_managed_product_image_key(
    object_key: str,
    public_prefix: str,
    allowed_extensions: frozenset[str],
) -> bool:
    filename = object_key.removeprefix(public_prefix)
    asset_id, separator, extension = filename.rpartition(".")
    if not separator or "/" in filename or extension not in allowed_extensions:
        return False
    try:
        return str(UUID(asset_id)) == asset_id
    except ValueError:
        return False


async def _read_and_validate_asset(
    storage: AssetObjectStorage,
    object_key: str,
    policy: AssetUploadPolicy,
    payload: AssetUploadCompletion,
) -> tuple[ObjectMetadata, ImageAssetMetadata]:
    metadata = await storage.head_object(object_key)
    _validate_object_metadata(policy, metadata, payload)
    data = await storage.read_object(object_key, metadata.etag, policy.max_size_bytes)
    if len(data) != metadata.size_bytes:
        raise InvalidAssetUploadError("Uploaded asset could not be read completely")

    if policy.validator is AssetValidator.IMAGE and policy.max_image_dimension is not None:
        asset_metadata = await asyncio.to_thread(
            _validate_product_image_bytes,
            data,
            payload.content_type,
            policy.max_image_dimension,
        )
        return metadata, asset_metadata

    raise RuntimeError(f"No asset validator is registered for {payload.purpose}")


def _asset_read(
    storage: AssetObjectStorage,
    upload_id: UUID,
    object_key: str,
    payload: AssetUploadCompletion,
    metadata: ObjectMetadata,
    asset_metadata: ImageAssetMetadata,
) -> AssetRead:
    return AssetRead(
        id=upload_id,
        purpose=payload.purpose,
        object_key=object_key,
        url=storage.public_url(object_key),
        content_type=payload.content_type,
        size_bytes=metadata.size_bytes,
        metadata=asset_metadata,
    )


async def _completed_asset(
    storage: AssetObjectStorage,
    upload_id: UUID,
    policy: AssetUploadPolicy,
    payload: AssetUploadCompletion,
) -> AssetRead:
    final_key = _final_key(policy, upload_id, payload.content_type)
    metadata, asset_metadata = await _read_and_validate_asset(
        storage,
        final_key,
        policy,
        payload,
    )
    return _asset_read(
        storage,
        upload_id,
        final_key,
        payload,
        metadata,
        asset_metadata,
    )


async def complete_asset_upload(
    storage: AssetObjectStorage,
    upload_id: UUID,
    payload: AssetUploadCompletion,
) -> AssetRead:
    policy = _policy_for(payload.purpose)
    _validate_descriptor(policy, payload.content_type, payload.size_bytes)
    staging_key = _staging_key(policy, upload_id)
    final_key = _final_key(policy, upload_id, payload.content_type)

    try:
        metadata, asset_metadata = await _read_and_validate_asset(
            storage,
            staging_key,
            policy,
            payload,
        )
    except AssetUploadNotFoundError:
        # Completing is idempotent when promotion succeeded but the client lost the response.
        return await _completed_asset(storage, upload_id, policy, payload)
    except InvalidAssetUploadError:
        await _delete_invalid_upload(storage, staging_key)
        raise

    try:
        await storage.promote_object(
            staging_key,
            final_key,
            payload.content_type,
            metadata.etag,
        )
    except AssetUploadNotFoundError:
        # Another completion can promote the same object between validation and copy.
        return await _completed_asset(storage, upload_id, policy, payload)
    except InvalidAssetUploadError:
        await _delete_invalid_upload(storage, staging_key)
        raise
    return _asset_read(
        storage,
        upload_id,
        final_key,
        payload,
        metadata,
        asset_metadata,
    )
