from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
