"""Compatibility exports for open-position administration."""

from backend.apps.open_positions.admin_routers import router
from backend.apps.open_positions.admin_service import (
    create_open_position,
    delete_open_position,
    get_open_position,
    list_open_positions,
    update_open_position,
)
from backend.apps.open_positions.exceptions import OpenPositionNotFoundError
from backend.apps.open_positions.repository import OPEN_POSITION_COLUMNS
from backend.apps.open_positions.repository import (
    open_position_from_record as _open_position_from_record,
)
from backend.apps.open_positions.schemas import (
    DescriptionText,
    LocalizedDescription,
    LocalizedShortText,
    OpenPositionCreate,
    OpenPositionListResponse,
    OpenPositionRead,
    OpenPositionUpdate,
    ShortText,
)
from backend.config.database import DbPool

__all__ = [
    "DbPool",
    "DescriptionText",
    "OPEN_POSITION_COLUMNS",
    "LocalizedDescription",
    "LocalizedShortText",
    "OpenPositionCreate",
    "OpenPositionListResponse",
    "OpenPositionNotFoundError",
    "OpenPositionRead",
    "OpenPositionUpdate",
    "ShortText",
    "_open_position_from_record",
    "create_open_position",
    "delete_open_position",
    "get_open_position",
    "list_open_positions",
    "router",
    "update_open_position",
]
