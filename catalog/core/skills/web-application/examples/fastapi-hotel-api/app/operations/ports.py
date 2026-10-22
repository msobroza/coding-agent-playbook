"""The ports the use cases consume: one narrow repository per aggregate and a unit of work."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol
from uuid import UUID

from app.domain.model import Booking, Customer, Room

# The SQL classes in app/db satisfy these structurally and never import this module;
# tests/fakes.py holds the in-memory twins.


class RoomRepository(Protocol):
    """Rooms by id, and pages of them ordered by number.

    Example: ``await hotel.rooms.get(room_id)`` -> a ``Room`` or RoomNotFoundError.
    """

    async def get(self, room_id: UUID) -> Room: ...  # raises RoomNotFoundError
    async def add(self, room: Room) -> None: ...
    async def save(self, room: Room) -> None: ...  # raises RoomNotFoundError
    async def list_page(self, *, limit: int, offset: int) -> list[Room]: ...  # by number
    async def count(self) -> int: ...


class CustomerRepository(Protocol):
    """Customers by id, one per email.

    Example: ``await hotel.customers.add(customer)``; a taken email raises DuplicateEmailError.
    """

    async def get(self, customer_id: UUID) -> Customer: ...  # raises CustomerNotFoundError
    async def add(self, customer: Customer) -> None: ...  # raises DuplicateEmailError


class BookingRepository(Protocol):
    """Bookings by id, and which nights of a room are still free.

    Example: ``await hotel.bookings.room_is_free(room_id, stay.nights)`` -> True or False.
    """

    async def get(self, booking_id: UUID) -> Booking: ...  # raises BookingNotFoundError
    async def room_is_free(self, room_id: UUID, nights: Sequence[date]) -> bool: ...
    async def add(self, booking: Booking) -> None: ...  # raises RoomUnavailableError
    # raises BookingNotFoundError for an unknown id
    async def cancel(self, booking_id: UUID, *, on: date) -> None: ...


class HotelUnitOfWork(Protocol):
    """The repositories of one request; ``commit`` makes all their writes durable at once.

    Example: ``await hotel.bookings.add(booking)`` then ``await hotel.commit()``.
    """

    @property
    def rooms(self) -> RoomRepository: ...
    @property
    def customers(self) -> CustomerRepository: ...
    @property
    def bookings(self) -> BookingRepository: ...
    async def commit(self) -> None: ...
