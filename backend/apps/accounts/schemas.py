from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserRead(BaseModel):
    id: UUID
    first_name: str | None
    last_name: str | None
    email: EmailStr
    registration_provider: str
    created_at: datetime
    updated_at: datetime


class UserIdentity(UserRead):
    firebase_uid: str
    sign_in_provider: str
    roles: frozenset[str]


class UserRecord(UserRead):
    firebase_uid: str | None
    is_active: bool
