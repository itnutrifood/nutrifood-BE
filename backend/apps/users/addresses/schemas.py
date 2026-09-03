from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.apps.users.addresses.enums import (
    AddressLocationSource,
    ArmeniaRegion,
    Country,
)

Latitude = Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
Longitude = Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
City = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Street = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
BuildingNumber = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=50),
]
Entrance = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Floor = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Apartment = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
AddressLabel = Annotated[str, StringConstraints(max_length=32)]
FormattedAddress = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


class AddressLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: Latitude
    longitude: Longitude


class AddressCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: AddressLocation
    label: AddressLabel | None = None
    entrance: Entrance | None = None
    floor: Floor | None = None
    apartment: Apartment | None = None
    is_default: bool = False


class AddressUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: AddressLocation | None = None
    label: AddressLabel | None = None
    entrance: Entrance | None = None
    floor: Floor | None = None
    apartment: Apartment | None = None
    is_default: bool | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")

        required_fields = {"location", "is_default"}
        for field_name in self.model_fields_set.intersection(required_fields):
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")

        return self


class AddressResolutionRead(BaseModel):
    country: Country
    region: ArmeniaRegion
    city: str
    street: str
    building_number: str
    formatted_address: FormattedAddress
    location: AddressLocation
    geocode_precision: str | None


class AddressRead(BaseModel):
    id: UUID
    label: str | None
    country: Country
    region: ArmeniaRegion
    city: str
    street: str
    building_number: str
    entrance: str | None
    floor: str | None
    apartment: str | None
    formatted_address: str | None
    location: AddressLocation | None
    location_source: AddressLocationSource
    geocode_precision: str | None
    is_default: bool
    created_at: datetime
    updated_at: datetime
