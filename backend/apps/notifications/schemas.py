from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

FcmPlatform = Literal["android", "ios", "web"]


class FcmTokenRegistration(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    token: str = Field(min_length=20, max_length=4096)
    platform: FcmPlatform


class FcmTokenRemoval(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    token: str = Field(min_length=20, max_length=4096)


class FcmInstallationRegistration(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    fid: str = Field(min_length=20, max_length=4096)
    platform: FcmPlatform


class FcmInstallationRemoval(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    fid: str = Field(min_length=20, max_length=4096)


class TestNotificationRead(BaseModel):
    message_id: str


class NotificationPreferencesRead(BaseModel):
    order_confirmations: bool
    delivery_updates: bool
    subscription_reminders: bool
    weekly_newsletter: bool
    promotional_offers: bool
    new_menu_items: bool


class NotificationPreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_confirmations: bool | None = None
    delivery_updates: bool | None = None
    subscription_reminders: bool | None = None
    weekly_newsletter: bool | None = None
    promotional_offers: bool | None = None
    new_menu_items: bool | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self
