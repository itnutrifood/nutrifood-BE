import asyncio
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote, urlsplit

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from backend.apps.assets.exceptions import (
    AssetStorageNotConfiguredError,
    AssetStorageUnavailableError,
    AssetUploadNotFoundError,
)
from backend.config.settings import Settings


@dataclass(frozen=True)
class ObjectMetadata:
    content_type: str
    size_bytes: int
    etag: str


class AssetObjectStorage(Protocol):
    def create_upload_url(self, object_key: str, content_type: str, expires_in: int) -> str: ...

    def public_url(self, object_key: str) -> str: ...

    async def head_object(self, object_key: str) -> ObjectMetadata: ...

    async def read_object(self, object_key: str, etag: str, max_bytes: int) -> bytes: ...

    async def promote_object(
        self,
        source_key: str,
        destination_key: str,
        content_type: str,
    ) -> None: ...

    async def delete_object(self, object_key: str) -> None: ...


class R2ObjectStorage:
    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        public_base_url: str,
    ) -> None:
        values = (
            endpoint_url,
            access_key_id,
            secret_access_key,
            bucket_name,
            public_base_url,
        )
        if not all(value.strip() for value in values):
            raise AssetStorageNotConfiguredError
        if not self._is_http_url(endpoint_url) or not self._is_http_url(public_base_url):
            raise AssetStorageNotConfiguredError

        self._bucket_name = bucket_name.strip()
        self._public_base_url = public_base_url.rstrip("/")
        self._client: Any = boto3.client(
            service_name="s3",
            endpoint_url=endpoint_url.rstrip("/"),
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                connect_timeout=5,
                read_timeout=15,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "R2ObjectStorage":
        return cls(
            endpoint_url=settings.r2_endpoint_url,
            access_key_id=settings.r2_access_key_id,
            secret_access_key=settings.r2_secret_access_key,
            bucket_name=settings.r2_bucket_name,
            public_base_url=settings.r2_public_base_url,
        )

    @staticmethod
    def _is_http_url(value: str) -> bool:
        parsed = urlsplit(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _is_not_found(exc: ClientError) -> bool:
        error = exc.response.get("Error", {})
        return error.get("Code") in {"404", "NoSuchKey", "NotFound"}

    def create_upload_url(self, object_key: str, content_type: str, expires_in: int) -> str:
        try:
            return str(
                self._client.generate_presigned_url(
                    "put_object",
                    Params={
                        "Bucket": self._bucket_name,
                        "Key": object_key,
                        "ContentType": content_type,
                    },
                    ExpiresIn=expires_in,
                )
            )
        except (BotoCoreError, ClientError) as exc:
            raise AssetStorageUnavailableError from exc

    def public_url(self, object_key: str) -> str:
        return f"{self._public_base_url}/{quote(object_key, safe='/')}"

    def _head_object(self, object_key: str) -> ObjectMetadata:
        try:
            response = self._client.head_object(Bucket=self._bucket_name, Key=object_key)
        except ClientError as exc:
            if self._is_not_found(exc):
                raise AssetUploadNotFoundError from exc
            raise AssetStorageUnavailableError from exc
        except BotoCoreError as exc:
            raise AssetStorageUnavailableError from exc

        return ObjectMetadata(
            content_type=str(response.get("ContentType", "")),
            size_bytes=int(response["ContentLength"]),
            etag=str(response["ETag"]),
        )

    async def head_object(self, object_key: str) -> ObjectMetadata:
        return await asyncio.to_thread(self._head_object, object_key)

    def _read_object(self, object_key: str, etag: str, max_bytes: int) -> bytes:
        try:
            response = self._client.get_object(
                Bucket=self._bucket_name,
                Key=object_key,
                IfMatch=etag,
            )
            body = response["Body"]
            try:
                return bytes(body.read(max_bytes + 1))
            finally:
                body.close()
        except ClientError as exc:
            if self._is_not_found(exc):
                raise AssetUploadNotFoundError from exc
            raise AssetStorageUnavailableError from exc
        except BotoCoreError as exc:
            raise AssetStorageUnavailableError from exc

    async def read_object(self, object_key: str, etag: str, max_bytes: int) -> bytes:
        return await asyncio.to_thread(self._read_object, object_key, etag, max_bytes)

    def _promote_object(
        self,
        source_key: str,
        destination_key: str,
        content_type: str,
    ) -> None:
        try:
            self._client.copy_object(
                Bucket=self._bucket_name,
                Key=destination_key,
                CopySource={"Bucket": self._bucket_name, "Key": source_key},
                ContentType=content_type,
                CacheControl="public, max-age=31536000, immutable",
                MetadataDirective="REPLACE",
            )
            self._client.delete_object(Bucket=self._bucket_name, Key=source_key)
        except (BotoCoreError, ClientError) as exc:
            raise AssetStorageUnavailableError from exc

    async def promote_object(
        self,
        source_key: str,
        destination_key: str,
        content_type: str,
    ) -> None:
        await asyncio.to_thread(
            self._promote_object,
            source_key,
            destination_key,
            content_type,
        )

    def _delete_object(self, object_key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket_name, Key=object_key)
        except (BotoCoreError, ClientError) as exc:
            raise AssetStorageUnavailableError from exc

    async def delete_object(self, object_key: str) -> None:
        await asyncio.to_thread(self._delete_object, object_key)
