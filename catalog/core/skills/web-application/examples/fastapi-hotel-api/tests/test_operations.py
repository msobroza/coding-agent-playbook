"""Use-case tests on the in-memory fakes: no database, no HTTP, fixed dates and ids."""

from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from app.domain.errors import InvalidStayError, RoomNotFoundError, RoomUnavailableError
from app.domain.model import Booking, Customer, Room, Stay
from app.operations.booking import book_room, cancel_booking
from app.operations.room import UNSET, RoomChanges, update_room
from tests.fakes import FakeHotelUnitOfWork

pytestmark = pytest.mark.anyio

MONDAY = date(2026, 3, 2)
ROOM = Room(UUID(int=1), "101", capacity=2, nightly_rate_cents=9_500, notes="sea view")
GUEST = Customer(UUID(int=2), "Ada Example", "ada@example.com")
BOOKING_ID = UUID(int=900)


@pytest.fixture
def hotel() -> FakeHotelUnitOfWork:
    return FakeHotelUnitOfWork(rooms=[ROOM], customers=[GUEST])


async def _book(
    hotel: FakeHotelUnitOfWork, check_in: date, check_out: date, booking_id: UUID = BOOKING_ID
) -> Booking:
    return await book_room(
        hotel,
        room_id=ROOM.room_id,
        customer_id=GUEST.customer_id,
        check_in=check_in,
        check_out=check_out,
        today=MONDAY,
        new_id=lambda: booking_id,
    )


@pytest.mark.parametrize(
    ("check_out", "price_cents"),
    [(date(2026, 3, 3), 9_500), (date(2026, 3, 7), 47_500)],
    ids=["one night", "five nights"],
)
async def test_booking_is_priced_per_night_in_cents(
    hotel: FakeHotelUnitOfWork, check_out: date, price_cents: int
) -> None:
    booking = await _book(hotel, MONDAY, check_out)

    assert booking == Booking(
        BOOKING_ID, ROOM.room_id, GUEST.customer_id, Stay(MONDAY, check_out), price_cents
    )
    assert hotel.commits == 1


async def test_booking_an_unknown_room_commits_nothing(hotel: FakeHotelUnitOfWork) -> None:
    missing = UUID(int=404)

    with pytest.raises(RoomNotFoundError) as raised:
        await book_room(
            hotel,
            room_id=missing,
            customer_id=GUEST.customer_id,
            check_in=MONDAY,
            check_out=date(2026, 3, 4),
            today=MONDAY,
            new_id=lambda: BOOKING_ID,
        )

    assert raised.value.room_id == missing
    assert hotel.commits == 0


async def test_an_overlapping_stay_is_refused_and_commits_nothing(
    hotel: FakeHotelUnitOfWork,
) -> None:
    await _book(hotel, MONDAY, date(2026, 3, 5))

    with pytest.raises(RoomUnavailableError):
        await _book(hotel, date(2026, 3, 4), date(2026, 3, 6), booking_id=UUID(int=901))

    assert hotel.commits == 1  # only the first booking


async def test_a_check_in_before_today_is_an_invalid_stay(hotel: FakeHotelUnitOfWork) -> None:
    with pytest.raises(InvalidStayError) as raised:
        await _book(hotel, date(2026, 3, 1), date(2026, 3, 3))

    assert raised.value.check_in == date(2026, 3, 1)
    assert hotel.commits == 0


async def test_a_cancelled_booking_frees_its_nights(hotel: FakeHotelUnitOfWork) -> None:
    await _book(hotel, MONDAY, date(2026, 3, 4))
    await cancel_booking(hotel, BOOKING_ID, today=MONDAY)

    rebooked = await _book(hotel, MONDAY, date(2026, 3, 4), booking_id=UUID(int=901))

    assert rebooked.booking_id == UUID(int=901)
    assert (await hotel.bookings.get(BOOKING_ID)).cancelled_on == MONDAY


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        (RoomChanges(notes=UNSET), ROOM),
        (RoomChanges(notes=None), Room(ROOM.room_id, "101", 2, 9_500, notes=None)),
        (RoomChanges(number="102"), Room(ROOM.room_id, "102", 2, 9_500, notes="sea view")),
    ],
    ids=["unset keeps notes", "none clears notes", "number changes alone"],
)
async def test_update_room_applies_only_the_fields_sent(
    hotel: FakeHotelUnitOfWork, changes: RoomChanges, expected: Room
) -> None:
    updated = await update_room(hotel, ROOM.room_id, changes)

    assert updated == expected
    assert await hotel.rooms.get(ROOM.room_id) == expected
    assert hotel.commits == 1
