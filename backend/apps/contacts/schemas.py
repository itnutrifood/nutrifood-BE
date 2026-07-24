from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from backend.apps.common.enums import ContactMessageStatus
from backend.apps.common.pagination import Page

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Subject = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Message = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)]


class ContactMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    email: EmailStr = Field(max_length=320)
    subject: Subject
    message: Message


class ContactMessageRead(BaseModel):
    id: UUID
    name: str
    email: str
    subject: str
    message: str
    status: ContactMessageStatus
    created_at: datetime
    updated_at: datetime


class ContactMessageListResponse(Page[ContactMessageRead]):
    pass


class ContactMessageStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ContactMessageStatus
