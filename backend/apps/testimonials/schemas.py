from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.apps.common.enums import TestimonialStatus
from backend.apps.common.pagination import Page

PersonName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=150),
]
AuthorTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
PhotoUrl = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2048),
]
Review = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=5000),
]
Rating = Annotated[int, Field(ge=1, le=5)]
SortOrder = Annotated[int, Field(ge=0, le=2_147_483_647)]


class TestimonialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: PersonName
    last_name: PersonName
    author_title: AuthorTitle
    photo_url: PhotoUrl | None = None
    review: Review
    rating: Rating
    status: TestimonialStatus = TestimonialStatus.ACTIVE
    sort_order: SortOrder = 0


class TestimonialUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: PersonName | None = None
    last_name: PersonName | None = None
    author_title: AuthorTitle | None = None
    photo_url: PhotoUrl | None = None
    review: Review | None = None
    rating: Rating | None = None
    status: TestimonialStatus | None = None
    sort_order: SortOrder | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")

        nullable_fields = {"photo_url"}
        for field_name in self.model_fields_set - nullable_fields:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")

        return self


class TestimonialRead(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    author_title: str
    photo_url: str | None
    review: str
    rating: int
    status: TestimonialStatus
    sort_order: int
    created_at: datetime
    updated_at: datetime


class TestimonialListResponse(Page[TestimonialRead]):
    pass


class PublicTestimonialRead(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    author_title: str
    photo_url: str | None
    review: str
    rating: int
    sort_order: int
    created_at: datetime
    updated_at: datetime
