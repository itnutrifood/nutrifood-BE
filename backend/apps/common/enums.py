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


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"


class OpenPositionStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class ContactMessageStatus(StrEnum):
    READ = "read"
    UNREAD = "unread"


class SubscriptionPlanStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class TestimonialStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
