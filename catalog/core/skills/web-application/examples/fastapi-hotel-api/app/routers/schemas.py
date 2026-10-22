"""Request and response models: they validate at the edge and never travel past the routes."""

from __future__ import annotations

from datetime import date
from typing import Any, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

#: The shape of a route's ``responses=`` argument; Any because FastAPI's own signature uses it.
ResponseDocs: TypeAlias = dict[int | str, dict[str, Any]]

_REQUEST = ConfigDict(extra="forbid")
_READ = ConfigDict(from_attributes=True)  # validates the domain records directly


class RoomCreate(BaseModel):
    """The body of POST /rooms.

    Example: ``{"number": "101", "capacity": 2, "nightly_rate_cents": 9500}``.
    """

    model_config = _REQUEST

    number: str = Field(min_length=1, max_length=10)
    capacity: int = Field(ge=1, le=10)
    nightly_rate_cents: int = Field(gt=0)
    notes: str | None = Field(default=None, max_length=500)


class RoomPatch(BaseModel):
    """Fields left out stay as they are; an explicit null clears ``notes`` only.

    Example: ``{"notes": null}`` clears the notes; ``{"number": null}`` answers 422.
    """

    model_config = _REQUEST

    number: str | None = Field(default=None, min_length=1, max_length=10)
    capacity: int | None = Field(default=None, ge=1, le=10)
    nightly_rate_cents: int | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("number", "capacity", "nightly_rate_cents")
    @classmethod
    def cannot_be_cleared(cls, value: str | int | None, info: ValidationInfo) -> str | int:
        """Refuse an explicit null for a field that cannot be cleared.

        Example: ``RoomPatch(number=None)`` raises a ValidationError naming ``number``.
        """
        if value is None:  # validators skip defaults, so this null was sent explicitly
            raise ValueError(
                f"{info.field_name} cannot be null: send a value or leave it out"
                " (only notes can be cleared)"
            )
        return value


class RoomRead(BaseModel):
    """A room as the API returns it.

    Example: ``RoomRead.model_validate(room)`` from a domain ``Room``.
    """

    model_config = _READ

    room_id: UUID
    number: str
    capacity: int
    nightly_rate_cents: int
    notes: str | None


class RoomPageRead(BaseModel):
    """One page of rooms as GET /rooms returns it, with the total count of rooms.

    Example: ``RoomPageRead.model_validate(await list_rooms(hotel, limit=20, offset=0))``.
    """

    model_config = _READ

    items: list[RoomRead]
    total: int
    limit: int
    offset: int


class CustomerCreate(BaseModel):
    """The body of POST /customers.

    Example: ``{"name": "Ada Example", "email": "ada@example.com"}``.
    """

    model_config = _REQUEST

    name: str = Field(min_length=1, max_length=120)
    # A constrained str: EmailStr would need the email-validator extra.
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")


class CustomerRead(BaseModel):
    """A customer as the API returns it.

    Example: ``CustomerRead.model_validate(customer)`` from a domain ``Customer``.
    """

    model_config = _READ

    customer_id: UUID
    name: str
    email: str


class BookingCreate(BaseModel):
    """The body of POST /bookings; the stay runs from check-in up to, not including, check-out.

    Example: ``{"room_id": "...", "customer_id": "...", "check_in": "2026-03-02",
    "check_out": "2026-03-05"}``.
    """

    model_config = _REQUEST

    room_id: UUID
    customer_id: UUID
    check_in: date
    check_out: date


class BookingRead(BaseModel):
    """A booking as the API returns it; ``cancelled_on`` is null while it is active.

    Example: ``BookingRead.model_validate(booking)`` from a domain ``Booking``.
    """

    model_config = _READ

    booking_id: UUID
    room_id: UUID
    customer_id: UUID
    check_in: date
    check_out: date
    price_cents: int
    cancelled_on: date | None
