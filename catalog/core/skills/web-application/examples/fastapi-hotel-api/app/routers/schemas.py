"""Request and response models: they validate at the edge and never travel past the routes."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_REQUEST = ConfigDict(extra="forbid")
_READ = ConfigDict(from_attributes=True)  # validates the domain records directly


class RoomCreate(BaseModel):
    model_config = _REQUEST

    number: str = Field(min_length=1, max_length=10)
    capacity: int = Field(ge=1, le=10)
    nightly_rate_cents: int = Field(gt=0)
    notes: str | None = Field(default=None, max_length=500)


class RoomPatch(BaseModel):
    """Fields left out stay as they are; an explicit null clears ``notes`` only."""

    model_config = _REQUEST

    number: str | None = Field(default=None, min_length=1, max_length=10)
    capacity: int | None = Field(default=None, ge=1, le=10)
    nightly_rate_cents: int | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("number", "capacity", "nightly_rate_cents")
    @classmethod
    def cannot_be_cleared(cls, value: str | int | None) -> str | int:
        if value is None:  # validators skip defaults, so this null was sent explicitly
            raise ValueError("this field cannot be null")
        return value


class RoomRead(BaseModel):
    model_config = _READ

    room_id: UUID
    number: str
    capacity: int
    nightly_rate_cents: int
    notes: str | None


class RoomPage(BaseModel):
    model_config = _READ

    items: list[RoomRead]
    total: int
    limit: int
    offset: int


class CustomerCreate(BaseModel):
    model_config = _REQUEST

    name: str = Field(min_length=1, max_length=120)
    # A constrained str: EmailStr would need the email-validator extra.
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")


class CustomerRead(BaseModel):
    model_config = _READ

    customer_id: UUID
    name: str
    email: str


class BookingCreate(BaseModel):
    model_config = _REQUEST

    room_id: UUID
    customer_id: UUID
    check_in: date
    check_out: date


class BookingRead(BaseModel):
    model_config = _READ

    booking_id: UUID
    room_id: UUID
    customer_id: UUID
    check_in: date
    check_out: date
    price_cents: int
    cancelled_on: date | None
