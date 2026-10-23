"""In-memory fakes of the ports; each raises the same domain errors as its SQL twin."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from uuid import UUID

from app.domain.errors import (
    BookingNotFoundError,
    CustomerNotFoundError,
    DuplicateEmailError,
    RoomNotFoundError,
    RoomUnavailableError,
)
from app.domain.model import Booking, Customer, Room


class InMemoryRoomRepository:
    """The RoomRepository port over a dict, ordered by number like the SQL one.

    Example: ``InMemoryRoomRepository(room)`` starts with one room.
    """

    def __init__(self, *rooms: Room) -> None:
        self.by_id = {room.room_id: room for room in rooms}

    async def get(self, room_id: UUID) -> Room:
        if room_id not in self.by_id:
            raise RoomNotFoundError(room_id)
        return self.by_id[room_id]

    async def add(self, room: Room) -> None:
        self.by_id[room.room_id] = room

    async def save(self, room: Room) -> None:
        await self.get(room.room_id)  # an unknown id fails here exactly as it does in SQL
        self.by_id[room.room_id] = room

    async def list_page(self, *, limit: int, offset: int) -> list[Room]:
        ordered = sorted(self.by_id.values(), key=lambda room: (room.number, room.room_id))
        return ordered[offset : offset + limit]

    async def count(self) -> int:
        return len(self.by_id)


class InMemoryCustomerRepository:
    """The CustomerRepository port over a dict; it refuses a taken email like the SQL one.

    Example: ``InMemoryCustomerRepository(customer)`` starts with one customer.
    """

    def __init__(self, *customers: Customer) -> None:
        self.by_id = {customer.customer_id: customer for customer in customers}

    async def get(self, customer_id: UUID) -> Customer:
        if customer_id not in self.by_id:
            raise CustomerNotFoundError(customer_id)
        return self.by_id[customer_id]

    async def add(self, customer: Customer) -> None:
        if any(known.email == customer.email for known in self.by_id.values()):
            raise DuplicateEmailError(customer.email)  # the SQL unique email refuses it too
        self.by_id[customer.customer_id] = customer


class InMemoryBookingRepository:
    """The BookingRepository port over a dict; it refuses an overlapping active night.

    Example: ``await InMemoryBookingRepository().add(booking)``.
    """

    def __init__(self) -> None:
        self.by_id: dict[UUID, Booking] = {}

    async def get(self, booking_id: UUID) -> Booking:
        if booking_id not in self.by_id:
            raise BookingNotFoundError(booking_id)
        return self.by_id[booking_id]

    async def room_is_free(self, room_id: UUID, nights: Sequence[date]) -> bool:
        active = (b for b in self.by_id.values() if b.room_id == room_id and not b.cancelled_on)
        taken = {night for booking in active for night in booking.stay.nights}
        return taken.isdisjoint(nights)

    async def add(self, booking: Booking) -> None:
        if not await self.room_is_free(booking.room_id, booking.stay.nights):
            # the SQL partial unique index refuses an overlapping night the same way
            raise RoomUnavailableError(booking.room_id, booking.check_in, booking.check_out)
        self.by_id[booking.booking_id] = booking

    async def cancel(self, booking_id: UUID, *, on: date) -> None:
        self.by_id[booking_id] = replace(await self.get(booking_id), cancelled_on=on)


class FakeHotelUnitOfWork:
    """The fake repositories plus a commit counter, so tests see what was made durable.

    Example: ``hotel = FakeHotelUnitOfWork(rooms=[room])``; after one use case,
    ``hotel.commits == 1``.
    """

    def __init__(self, *, rooms: Sequence[Room] = (), customers: Sequence[Customer] = ()) -> None:
        self.rooms = InMemoryRoomRepository(*rooms)
        self.customers = InMemoryCustomerRepository(*customers)
        self.bookings = InMemoryBookingRepository()
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1
