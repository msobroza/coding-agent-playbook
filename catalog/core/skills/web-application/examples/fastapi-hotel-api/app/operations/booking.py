"""Booking use cases: book a room for a stay, read a booking, cancel it."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from uuid import UUID

from app.domain.errors import InvalidStayError, RoomUnavailableError
from app.domain.model import Booking, Stay, open_booking
from app.operations.ports import HotelUnitOfWork


async def book_room(
    hotel: HotelUnitOfWork,
    *,
    room_id: UUID,
    customer_id: UUID,
    check_in: date,
    check_out: date,
    today: date,
    new_id: Callable[[], UUID],
) -> Booking:
    """Book ``room_id`` for ``customer_id`` from ``check_in`` to ``check_out``; commit once.

    Example: ``await book_room(hotel, room_id=r, customer_id=c, check_in=d1, check_out=d2,
    today=d0, new_id=uuid4)`` -> the new ``Booking``, priced in integer cents.
    """
    room = await hotel.rooms.get(room_id)
    customer = await hotel.customers.get(customer_id)
    stay = Stay(check_in, check_out)
    if check_in < today:
        raise InvalidStayError(check_in, check_out, f"check-in is before today, {today}")
    if not await hotel.bookings.room_is_free(room_id, stay.nights):
        raise RoomUnavailableError(room_id, check_in, check_out)
    booking = open_booking(new_id(), room, customer, stay)
    await hotel.bookings.add(booking)  # the database refuses a lost race the same way
    await hotel.commit()
    return booking


async def get_booking(hotel: HotelUnitOfWork, booking_id: UUID) -> Booking:
    """The booking ``booking_id``, cancelled or not; an unknown id raises BookingNotFoundError.

    Example: ``(await get_booking(hotel, booking_id)).cancelled_on`` -> None while active.
    """
    return await hotel.bookings.get(booking_id)


async def cancel_booking(hotel: HotelUnitOfWork, booking_id: UUID, *, today: date) -> None:
    """Mark the booking and its nights cancelled on ``today``; cancelling twice changes nothing.

    Example: ``await cancel_booking(hotel, booking_id, today=date(2026, 3, 2))`` frees the
    booking's nights; an unknown id raises BookingNotFoundError.
    """
    booking = await hotel.bookings.get(booking_id)
    if booking.cancelled_on is not None:
        return
    await hotel.bookings.cancel(booking_id, on=today)
    await hotel.commit()
