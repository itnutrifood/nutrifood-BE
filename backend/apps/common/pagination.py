import base64
import binascii
import json
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from pydantic import BaseModel

from backend.apps.common.exceptions import InvalidCursorError as InvalidCursorError


class CursorPage[T](BaseModel):
    items: list[T]
    limit: int
    next_cursor: str | None


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    limit: int
    total_pages: int


def page_offset(page: int, limit: int) -> int:
    return (page - 1) * limit


def page_count(total: int, limit: int) -> int:
    if total <= 0:
        return 0
    return (total + limit - 1) // limit


def encode_cursor(payload: Mapping[str, object]) -> str:
    cursor_json = json.dumps(
        payload,
        default=_serialize_cursor_value,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(cursor_json.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> dict[str, object]:
    if not cursor:
        raise InvalidCursorError("Cursor cannot be empty")

    try:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.b64decode(
            f"{cursor}{padding}".encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
        payload = json.loads(decoded.decode("utf-8"))
    except (
        binascii.Error,
        UnicodeEncodeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise InvalidCursorError("Invalid cursor") from exc

    if not isinstance(payload, dict):
        raise InvalidCursorError("Invalid cursor")

    return cast(dict[str, object], payload)


def _serialize_cursor_value(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal | UUID):
        return str(value)

    raise TypeError(f"Object of type {type(value).__name__} is not cursor serializable")
