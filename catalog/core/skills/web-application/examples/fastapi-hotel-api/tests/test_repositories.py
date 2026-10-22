"""One contract suite for the repositories, run against the fakes and against SQL.

The SQL side runs on the real engine in a rolled-back transaction. Its overlap
test calls the repository directly, without the use case's availability check:
the partial unique index refuses the second booking, and the repository turns
the driver error into the same RoomUnavailableError the fake raises.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import SqlHotelUnitOfWork
from app.domain.errors import (
    BookingNotFoundError,
    CustomerNotFoundError,
    DuplicateEmailError,
    NotFoundError,
    RoomNotFoundError,
    RoomUnavailableError,
)
from app.domain.model import Booking, Customer, Room, Stay
from app.operations.ports import HotelUnitOfWork
from tests.fakes import FakeHotelUnitOfWork

pytestmark = pytest.mark.anyio

ROOM = Room(UUID(int=1), "101", capacity=2, nightly_rate_cents=9_500)
GUEST = Customer(UUID(int=2), "Ada Example", "ada@example.com")


def _booking(number: int, check_in: date, check_out: date) -> Booking:
    stay = Stay(check_in, check_out)
    return Booking(UUID(int=900 + number), ROOM.room_id, GUEST.customer_id, stay, 19_000)


@pytest.fixture(params=["fake", "sql"], ids=["fake", "sql"])
def empty_hotel(request: pytest.FixtureRequest) -> HotelUnitOfWork:
    if request.param == "fake":
        return FakeHotelUnitOfWork()
    session: AsyncSession = request.getfixturevalue("session")  # only the SQL side needs it
    return SqlHotelUnitOfWork(session)


@pytest.fixture
async def hotel(empty_hotel: HotelUnitOfWork) -> HotelUnitOfWork:
    await empty_hotel.rooms.add(ROOM)
    await empty_hotel.customers.add(GUEST)
    return empty_hotel


async def test_an_overlapping_active_booking_is_refused(hotel: HotelUnitOfWork) -> None:
    await hotel.bookings.add(_booking(1, date(2026, 3, 2), date(2026, 3, 5)))

    with pytest.raises(RoomUnavailableError):
        await hotel.bookings.add(_booking(2, date(2026, 3, 4), date(2026, 3, 6)))


async def test_a_stay_starting_on_the_previous_check_out_day_is_free(
    hotel: HotelUnitOfWork,
) -> None:
    await hotel.bookings.add(_booking(1, date(2026, 3, 2), date(2026, 3, 5)))
    following = _booking(2, date(2026, 3, 5), date(2026, 3, 7))

    assert await hotel.bookings.room_is_free(ROOM.room_id, following.stay.nights)
    await hotel.bookings.add(following)
    assert await hotel.bookings.get(following.booking_id) == following


async def test_a_cancelled_bookings_nights_can_be_booked_again(hotel: HotelUnitOfWork) -> None:
    first = _booking(1, date(2026, 3, 2), date(2026, 3, 5))
    await hotel.bookings.add(first)
    await hotel.bookings.cancel(first.booking_id, on=date(2026, 3, 1))

    await hotel.bookings.add(_booking(2, date(2026, 3, 2), date(2026, 3, 5)))

    assert (await hotel.bookings.get(first.booking_id)).cancelled_on == date(2026, 3, 1)


async def test_a_duplicate_email_is_refused(hotel: HotelUnitOfWork) -> None:
    with pytest.raises(DuplicateEmailError) as raised:
        await hotel.customers.add(Customer(UUID(int=3), "Ada Again", GUEST.email))

    assert raised.value.email == GUEST.email


@pytest.mark.parametrize(
    ("repository", "error"),
    [
        ("rooms", RoomNotFoundError),
        ("customers", CustomerNotFoundError),
        ("bookings", BookingNotFoundError),
    ],
    ids=["room", "customer", "booking"],
)
async def test_an_unknown_id_raises_the_matching_not_found_error(
    hotel: HotelUnitOfWork, repository: str, error: type[NotFoundError]
) -> None:
    with pytest.raises(error):
        await getattr(hotel, repository).get(UUID(int=404))
