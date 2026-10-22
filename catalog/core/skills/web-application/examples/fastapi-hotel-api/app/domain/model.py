"""Typed records of the hotel and its one pricing rule, free of FastAPI, Pydantic and SQLAlchemy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from app.domain.errors import InvalidStayError


@dataclass(frozen=True)
class Room:
    """A bookable room and its nightly rate in integer cents.

    Example: ``Room(room_id, "101", capacity=2, nightly_rate_cents=9_500)``.
    """

    room_id: UUID
    number: str
    capacity: int
    nightly_rate_cents: int  # money is integer cents, never float
    notes: str | None = None


@dataclass(frozen=True)
class Customer:
    """A registered customer; the email is unique among customers.

    Example: ``Customer(customer_id, "Ada Example", "ada@example.com")``.
    """

    customer_id: UUID
    name: str
    email: str


@dataclass(frozen=True)
class Stay:
    """The nights from ``check_in`` up to, not including, ``check_out``.

    Example: ``Stay(date(2026, 3, 2), date(2026, 3, 4)).nights`` -> March 2 and March 3;
    a check-out on or before the check-in raises InvalidStayError.
    """

    check_in: date
    check_out: date

    def __post_init__(self) -> None:
        if self.check_in >= self.check_out:
            raise InvalidStayError(self.check_in, self.check_out, "check-out must follow check-in")

    @property
    def nights(self) -> tuple[date, ...]:
        count = (self.check_out - self.check_in).days
        return tuple(self.check_in + timedelta(days=offset) for offset in range(count))


@dataclass(frozen=True)
class Booking:
    """One customer's booking of one room for a stay, priced in integer cents.

    Example: ``open_booking(booking_id, room, customer, stay)`` builds an active one;
    ``cancelled_on`` is set once it is cancelled.
    """

    booking_id: UUID
    room_id: UUID
    customer_id: UUID
    stay: Stay
    price_cents: int
    cancelled_on: date | None = None

    @property
    def check_in(self) -> date:
        return self.stay.check_in

    @property
    def check_out(self) -> date:
        return self.stay.check_out


def price_stay(room: Room, stay: Stay) -> int:
    """The price of ``stay`` in ``room``: one nightly rate per night, in integer cents.

    Example: two nights at 9_500 cents -> ``price_stay(room, stay) == 19_000``.
    """
    return len(stay.nights) * room.nightly_rate_cents


def open_booking(booking_id: UUID, room: Room, customer: Customer, stay: Stay) -> Booking:
    """A new, active booking of ``room`` for ``customer``, priced by :func:`price_stay`.

    Example: ``open_booking(uuid4(), room, customer, stay).price_cents == price_stay(room, stay)``.
    """
    return Booking(booking_id, room.room_id, customer.customer_id, stay, price_stay(room, stay))
