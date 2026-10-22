"""The hotel's own failures: one base class, and one subclass per outcome a client sees."""

from __future__ import annotations

from datetime import date
from uuid import UUID


class HotelError(Exception):
    """Root of the hotel's own failures; the app maps its subclasses to status codes.

    Example: ``app.add_exception_handler(HotelError, hotel_error_response)`` in create_app.
    """


class NotFoundError(HotelError):
    """A record the caller asked for does not exist; the app answers 404.

    Example: ``except NotFoundError`` catches a missing room, customer or booking alike.
    """


class RoomNotFoundError(NotFoundError):
    """No room has ``room_id``.

    Example: ``raise RoomNotFoundError(room_id)`` -> "no room with id <room_id>".
    """

    def __init__(self, room_id: UUID) -> None:
        super().__init__(f"no room with id {room_id}")
        self.room_id = room_id


class CustomerNotFoundError(NotFoundError):
    """No customer has ``customer_id``.

    Example: ``raise CustomerNotFoundError(customer_id)`` -> "no customer with id <id>".
    """

    def __init__(self, customer_id: UUID) -> None:
        super().__init__(f"no customer with id {customer_id}")
        self.customer_id = customer_id


class BookingNotFoundError(NotFoundError):
    """No booking has ``booking_id``.

    Example: ``raise BookingNotFoundError(booking_id)`` -> "no booking with id <id>".
    """

    def __init__(self, booking_id: UUID) -> None:
        super().__init__(f"no booking with id {booking_id}")
        self.booking_id = booking_id


class ConflictError(HotelError):
    """The request clashes with the current state of another record; the app answers 409.

    Example: ``except ConflictError`` catches a booked room and a taken email alike.
    """


class RoomUnavailableError(ConflictError):
    """An active booking already holds one of the nights from ``check_in`` to ``check_out``.

    Example: ``raise RoomUnavailableError(room_id, date(2026, 3, 2), date(2026, 3, 5))``.
    """

    def __init__(self, room_id: UUID, check_in: date, check_out: date) -> None:
        super().__init__(f"room {room_id} is already booked between {check_in} and {check_out}")
        self.room_id = room_id
        self.check_in = check_in
        self.check_out = check_out


class DuplicateEmailError(ConflictError):
    """A customer with ``email`` is already registered.

    Example: ``raise DuplicateEmailError("ada@example.com")``.
    """

    def __init__(self, email: str) -> None:
        super().__init__(f"a customer with email {email} is already registered")
        self.email = email


class InvalidStayError(HotelError):
    """A stay whose dates cannot be booked; ``reason`` says which rule they break.

    Example: ``raise InvalidStayError(check_in, check_out, "check-out must follow check-in")``.
    """

    def __init__(self, check_in: date, check_out: date, reason: str) -> None:
        super().__init__(f"cannot book {check_in} to {check_out}: {reason}")
        self.check_in = check_in
        self.check_out = check_out
        self.reason = reason
