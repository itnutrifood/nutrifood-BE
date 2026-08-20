from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from backend.apps.users.addresses.enums import ArmeniaRegion, Country

City = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Street = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
BuildingNumber = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=50),
]
Entrance = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Floor = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class AddressCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    country: Country = Country.ARMENIA
    region: ArmeniaRegion
    city: City
    street: Street
    building_number: BuildingNumber
    entrance: Entrance | None = None
    floor: Floor | None = None
    is_default: bool = False


class AddressUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    country: Country | None = None
    region: ArmeniaRegion | None = None
    city: City | None = None
    street: Street | None = None
    building_number: BuildingNumber | None = None
    entrance: Entrance | None = None
    floor: Floor | None = None
    is_default: bool | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")

        required_fields = {
            "country",
            "region",
            "city",
            "street",
            "building_number",
            "is_default",
        }
        for field_name in self.model_fields_set.intersection(required_fields):
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")

        return self


class AddressRead(BaseModel):
    id: UUID
    country: Country
    region: ArmeniaRegion
    city: str
    street: str
    building_number: str
    entrance: str | None
    floor: str | None
    is_default: bool
    created_at: datetime
    updated_at: datetime
