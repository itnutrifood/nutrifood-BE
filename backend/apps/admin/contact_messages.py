"""Compatibility exports for contact-message administration."""

from backend.apps.contacts.admin_routers import router
from backend.apps.contacts.exceptions import ContactMessageNotFoundError
from backend.apps.contacts.schemas import (
    ContactMessageListResponse,
    ContactMessageRead,
    ContactMessageStatusUpdate,
)
from backend.apps.contacts.service import (
    get_contact_message,
    list_contact_messages,
    update_contact_message_status,
)
from backend.config.database import DbPool

__all__ = [
    "ContactMessageListResponse",
    "ContactMessageNotFoundError",
    "ContactMessageRead",
    "ContactMessageStatusUpdate",
    "DbPool",
    "get_contact_message",
    "list_contact_messages",
    "router",
    "update_contact_message_status",
]
