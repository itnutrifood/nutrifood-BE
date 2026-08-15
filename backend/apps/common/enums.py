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


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    READY_FOR_DELIVERY = "ready_for_delivery"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class PaymentMethod(StrEnum):
    CASH_ON_DELIVERY = "cash_on_delivery"
    POS = "pos"


class PaymentStatus(StrEnum):
    UNPAID = "unpaid"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"
