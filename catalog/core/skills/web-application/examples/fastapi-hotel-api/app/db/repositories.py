"""SQL repositories that map rows to domain records, and the unit of work that commits them."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BookingRow, CustomerRow, RoomNightRow, RoomRow
from app.domain.errors import (
    BookingNotFoundError,
    CustomerNotFoundError,
    DuplicateEmailError,
    RoomNotFoundError,
    RoomUnavailableError,
)
from app.domain.model import Booking, Customer, Room, Stay

# Repositories add and flush but never commit: the use case calls
# SqlHotelUnitOfWork.commit once. Driver errors stop here, translated into the
# domain errors the ports name.


def _room(row: RoomRow) -> Room:
    return Room(row.room_id, row.number, row.capacity, row.nightly_rate_cents, row.notes)


def _booking(row: BookingRow) -> Booking:
    stay = Stay(row.check_in, row.check_out)
    return Booking(
        row.booking_id, row.room_id, row.customer_id, stay, row.price_cents, row.cancelled_on
    )


class SqlRoomRepository:
    """The RoomRepository port over the request's session.

    Example: ``await SqlRoomRepository(session).list_page(limit=20, offset=0)``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, room_id: UUID) -> Room:
        return _room(await self._row(room_id))

    async def add(self, room: Room) -> None:
        self._session.add(
            RoomRow(
                room_id=room.room_id,
                number=room.number,
                capacity=room.capacity,
                nightly_rate_cents=room.nightly_rate_cents,
                notes=room.notes,
            )
        )
        await self._session.flush()

    async def save(self, room: Room) -> None:
        row = await self._row(room.room_id)
        row.number, row.capacity = room.number, room.capacity
        row.nightly_rate_cents, row.notes = room.nightly_rate_cents, room.notes
        await self._session.flush()

    async def list_page(self, *, limit: int, offset: int) -> list[Room]:
        stmt = select(RoomRow).order_by(RoomRow.number, RoomRow.room_id)
        rows = await self._session.scalars(stmt.limit(limit).offset(offset))
        return [_room(row) for row in rows]

    async def count(self) -> int:
        return await self._session.scalar(select(func.count()).select_from(RoomRow)) or 0

    async def _row(self, room_id: UUID) -> RoomRow:
        row = await self._session.get(RoomRow, room_id)
        if row is None:
            raise RoomNotFoundError(room_id)
        return row


class SqlCustomerRepository:
    """The CustomerRepository port over the request's session.

    Example: ``await SqlCustomerRepository(session).get(customer_id)``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, customer_id: UUID) -> Customer:
        row = await self._row(customer_id)
        return Customer(row.customer_id, row.name, row.email)

    async def add(self, customer: Customer) -> None:
        row = CustomerRow(
            customer_id=customer.customer_id, name=customer.name, email=customer.email
        )
        self._session.add(row)
        try:
            await self._session.flush()
        # The unique email is the only constraint a new customer row can break.
        except IntegrityError as exc:
            raise DuplicateEmailError(customer.email) from exc

    async def _row(self, customer_id: UUID) -> CustomerRow:
        row = await self._session.get(CustomerRow, customer_id)
        if row is None:
            raise CustomerNotFoundError(customer_id)
        return row


class SqlBookingRepository:
    """The BookingRepository port over the request's session.

    Example: ``await SqlBookingRepository(session).cancel(booking_id, on=today)``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, booking_id: UUID) -> Booking:
        return _booking(await self._row(booking_id))

    async def room_is_free(self, room_id: UUID, nights: Sequence[date]) -> bool:
        stmt = select(RoomNightRow.night).where(
            RoomNightRow.room_id == room_id,
            RoomNightRow.night.in_(nights),  # bound parameters, never a built SQL string
            RoomNightRow.cancelled_on.is_(None),
        )
        return await self._session.scalar(stmt.limit(1)) is None

    async def add(self, booking: Booking) -> None:
        nights = [RoomNightRow(room_id=booking.room_id, night=n) for n in booking.stay.nights]
        row = BookingRow(
            booking_id=booking.booking_id,
            room_id=booking.room_id,
            customer_id=booking.customer_id,
            check_in=booking.check_in,
            check_out=booking.check_out,
            price_cents=booking.price_cents,
            cancelled_on=booking.cancelled_on,
            nights=nights,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        # A new booking can only break one_active_booking_per_room_night.
        except IntegrityError as exc:
            raise RoomUnavailableError(
                booking.room_id, booking.check_in, booking.check_out
            ) from exc

    async def cancel(self, booking_id: UUID, *, on: date) -> None:
        await self._row(booking_id)  # an unknown id fails here, as it does in the fake
        await self._session.execute(
            update(BookingRow).where(BookingRow.booking_id == booking_id).values(cancelled_on=on)
        )
        await self._session.execute(
            update(RoomNightRow)
            .where(RoomNightRow.booking_id == booking_id)
            .values(cancelled_on=on)
        )

    async def _row(self, booking_id: UUID) -> BookingRow:
        row = await self._session.get(BookingRow, booking_id)
        if row is None:
            raise BookingNotFoundError(booking_id)
        return row


class SqlHotelUnitOfWork:
    """The repositories share the request's session, so one commit covers all of them.

    Example: ``hotel = SqlHotelUnitOfWork(session)``, then ``await hotel.commit()`` once.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.rooms = SqlRoomRepository(session)
        self.customers = SqlCustomerRepository(session)
        self.bookings = SqlBookingRepository(session)

    async def commit(self) -> None:
        await self._session.commit()
