"""Room use cases: typed inputs in, domain records out, one commit per write."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from typing import Final, TypeVar
from uuid import UUID

from app.domain.model import Room
from app.operations.ports import HotelUnitOfWork

_Value = TypeVar("_Value")


class Unset(Enum):
    """The type of :data:`UNSET`, a one-member enum so type checkers can narrow it away.

    Example: ``number: str | Unset = UNSET`` declares a field a partial update may leave out.
    """

    TOKEN = 0


#: A field left out of a partial update: keep the current value.
UNSET: Final = Unset.TOKEN


@dataclass(frozen=True)
class RoomChanges:
    """A partial update: UNSET keeps the current value, None clears ``notes``.

    Example: ``RoomChanges(notes=None)`` clears the notes and keeps every other field.
    """

    number: str | Unset = UNSET
    capacity: int | Unset = UNSET
    nightly_rate_cents: int | Unset = UNSET
    notes: str | Unset | None = UNSET


@dataclass(frozen=True)
class RoomPage:
    """One bounded page of rooms ordered by number, and how many rooms exist in all.

    Example: ``(await list_rooms(hotel, limit=20, offset=0)).total`` -> every room's count.
    """

    items: tuple[Room, ...]
    total: int
    limit: int
    offset: int


def _keep_or(change: _Value | Unset, current: _Value) -> _Value:
    return current if change is UNSET else change


async def create_room(
    hotel: HotelUnitOfWork,
    *,
    number: str,
    capacity: int,
    nightly_rate_cents: int,
    notes: str | None,
    new_id: Callable[[], UUID],
) -> Room:
    """Add a room under a new id and commit once.

    Example: ``await create_room(hotel, number="101", capacity=2, nightly_rate_cents=9_500,
    notes=None, new_id=uuid4)`` -> the new ``Room``.
    """
    room = Room(new_id(), number, capacity, nightly_rate_cents, notes)
    await hotel.rooms.add(room)
    await hotel.commit()
    return room


async def get_room(hotel: HotelUnitOfWork, room_id: UUID) -> Room:
    """The room ``room_id``; an unknown id raises RoomNotFoundError.

    Example: ``(await get_room(hotel, room_id)).number`` -> "101".
    """
    return await hotel.rooms.get(room_id)


async def list_rooms(hotel: HotelUnitOfWork, *, limit: int, offset: int) -> RoomPage:
    """One page of rooms ordered by number, with the total count of rooms.

    Example: ``await list_rooms(hotel, limit=20, offset=40)`` -> the third page of 20.
    """
    items = await hotel.rooms.list_page(limit=limit, offset=offset)
    return RoomPage(tuple(items), await hotel.rooms.count(), limit, offset)


async def update_room(hotel: HotelUnitOfWork, room_id: UUID, changes: RoomChanges) -> Room:
    """Apply only the fields ``changes`` sets to the room ``room_id`` and commit once.

    Example: ``await update_room(hotel, room_id, RoomChanges(number="102"))`` -> the room
    with its new number; an unknown id raises RoomNotFoundError.
    """
    room = await hotel.rooms.get(room_id)
    updated = replace(
        room,
        number=_keep_or(changes.number, room.number),
        capacity=_keep_or(changes.capacity, room.capacity),
        nightly_rate_cents=_keep_or(changes.nightly_rate_cents, room.nightly_rate_cents),
        notes=_keep_or(changes.notes, room.notes),
    )
    await hotel.rooms.save(updated)
    await hotel.commit()
    return updated
