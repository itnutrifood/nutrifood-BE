from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AdminUser(BaseModel):
    id: UUID
    username: str
    token_version: int


class AdminRecord(AdminUser):
    password_hash: str
    is_active: bool


class AdminLoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str | None = Field(default=None, min_length=1)
    email: str | None = Field(default=None, min_length=1)
    password: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identifier(self) -> Self:
        if self.username is None and self.email is None:
            raise ValueError("Username or email is required")
        return self

    @property
    def identifier(self) -> str:
        identifier = self.username or self.email
        if identifier is None:
            raise ValueError("Username or email is required")
        return identifier


class AdminRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class AdminTokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int
