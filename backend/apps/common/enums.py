from enum import StrEnum


class LanguageCode(StrEnum):
    HY_AM = "HY-AM"
    EN_US = "EN-US"
    RU_RU = "RU-RU"


class CategoryStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class FAQStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class SubscriptionPlanStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
