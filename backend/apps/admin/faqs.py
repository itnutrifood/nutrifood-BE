"""Compatibility exports for FAQ administration."""

from backend.apps.faqs.admin_routers import router
from backend.apps.faqs.admin_service import (
    create_faq,
    delete_faq,
    get_faq,
    list_faqs,
    update_faq,
)
from backend.apps.faqs.exceptions import DuplicateFAQSlugError, FAQNotFoundError
from backend.apps.faqs.repository import FAQ_COLUMNS
from backend.apps.faqs.repository import faq_from_record as _faq_from_record
from backend.apps.faqs.schemas import (
    AnswerValue,
    FAQCreate,
    FAQListResponse,
    FAQRead,
    FAQSlug,
    FAQUpdate,
    LocalizedAnswer,
    LocalizedQuestion,
    QuestionValue,
    SortOrder,
)
from backend.config.database import DbPool

__all__ = [
    "AnswerValue",
    "DbPool",
    "FAQ_COLUMNS",
    "DuplicateFAQSlugError",
    "FAQCreate",
    "FAQListResponse",
    "FAQNotFoundError",
    "FAQRead",
    "FAQSlug",
    "FAQUpdate",
    "LocalizedAnswer",
    "LocalizedQuestion",
    "QuestionValue",
    "SortOrder",
    "_faq_from_record",
    "create_faq",
    "delete_faq",
    "get_faq",
    "list_faqs",
    "router",
    "update_faq",
]
