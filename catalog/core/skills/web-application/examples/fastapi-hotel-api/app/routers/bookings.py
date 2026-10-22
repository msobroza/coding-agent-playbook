"""Booking routes: book a room, read a booking, cancel it.

Every failure comes from the error table in create_app; no route catches a domain error.
"""

from __future__ import annotations

from typing import Any, Final
from uuid import UUID

from fastapi import APIRouter, Request, Response, status

from app.deps import HotelDep, NewIdDep, TodayDep
from app.operations import booking as booking_ops
from app.routers.schemas import BookingCreate, BookingRead

router = APIRouter(prefix="/bookings", tags=["bookings"])

NOT_FOUND: Final[dict[int | str, dict[str, Any]]] = {404: {"description": "No booking has this id"}}
BOOKING_REFUSED: Final[dict[int | str, dict[str, Any]]] = {
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


@router.get("/{booking_id}", summary="Read a booking", responses=NOT_FOUND)
async def read_booking(booking_id: UUID, hotel: HotelDep) -> BookingRead:
    return BookingRead.model_validate(await booking_ops.get_booking(hotel, booking_id))


@router.delete(
    "/{booking_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel a booking",
    responses=NOT_FOUND,
)
async def cancel_booking(booking_id: UUID, hotel: HotelDep, today: TodayDep) -> None:
    await booking_ops.cancel_booking(hotel, booking_id, today=today)
