"""Booking routes: book a room, read a booking, cancel it."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from fastapi import APIRouter, Request, Response, status

from app.deps import HotelDep, NewIdDep, TodayDep
from app.operations import booking as booking_ops
from app.routers.schemas import BookingCreate, BookingRead, ResponseDocs

# Every failure comes from the error table in create_app; no route catches a domain error.

router = APIRouter(prefix="/bookings", tags=["bookings"])

BOOKING_NOT_FOUND: Final[ResponseDocs] = {404: {"description": "No booking has this id"}}
BOOKING_REFUSED: Final[ResponseDocs] = {
    404: {"description": "No room or no customer has this id"},
    409: {"description": "The room is already booked for one of these nights"},
    422: {"description": "The stay is empty, reversed or starts in the past"},
}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Book a room for a stay",
    responses=BOOKING_REFUSED,
)
async def book_room(
    body: BookingCreate,
    hotel: HotelDep,
    today: TodayDep,
    new_id: NewIdDep,
    request: Request,
    response: Response,
) -> BookingRead:
    """Book a room for a stay and answer 201 with a Location header naming the booking.

    Example: ``POST /bookings {"room_id": ..., "customer_id": ..., "check_in": "2026-03-02",
    "check_out": "2026-03-05"}`` -> 201 with the price in integer cents.
    """
    booking = await booking_ops.book_room(
        hotel,
        room_id=body.room_id,
        customer_id=body.customer_id,
        check_in=body.check_in,
        check_out=body.check_out,
        today=today,
        new_id=new_id,
    )
    location = request.url_for("read_booking", booking_id=booking.booking_id)
    response.headers["Location"] = location.path
    return BookingRead.model_validate(booking)


@router.get("/{booking_id}", summary="Read a booking", responses=BOOKING_NOT_FOUND)
async def read_booking(booking_id: UUID, hotel: HotelDep) -> BookingRead:
    """The booking ``booking_id``, cancelled or not, or 404.

    Example: ``GET /bookings/{booking_id}`` -> 200; ``cancelled_on`` is null while active.
    """
    return BookingRead.model_validate(await booking_ops.get_booking(hotel, booking_id))


@router.delete(
    "/{booking_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel a booking",
    responses=BOOKING_NOT_FOUND,
)
async def cancel_booking(booking_id: UUID, hotel: HotelDep, today: TodayDep) -> None:
    """Cancel the booking and free its nights; cancelling twice answers 204 again.

    Example: ``DELETE /bookings/{booking_id}`` -> 204 with no body.
    """
    await booking_ops.cancel_booking(hotel, booking_id, today=today)
