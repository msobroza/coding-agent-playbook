"""Room use cases: typed inputs in, domain records out, one commit per write."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from typing import Final
from uuid import UUID

from app.domain.model import Room
from app.operations.ports import HotelUnitOfWork


class Unset(Enum):
    TOKEN = 0


#: A field left out of a partial update: keep the current value.
UNSET: Final = Unset.TOKEN


@dataclass(frozen=True)
class RoomChanges:
    """A partial update: UNSET keeps the current value, None clears ``notes``."""

    number: str | Unset = UNSET
    capacity: int | Unset = UNSET
    nightly_rate_cents: int | Unset = UNSET
    notes: str | Unset | None = UNSET


@dataclass(frozen=True)
class RoomPage:
    """One bounded page of rooms ordered by number, and how many rooms exist in all."""

    items: tuple[Room, ...]
    total: int
    limit: int
    offset: int


async def create_room(
    hotel: HotelUnitOfWork,
    *,
    number: str,
    capacity: int,
    nightly_rate_cents: int,
    notes: str | None,
    new_id: Callable[[], UUID],
) -> Room:
    room = Room(new_id(), number, capacity, nightly_rate_cents, notes)
    await hotel.rooms.add(room)
    await hotel.commit()
    return room


async def get_room(hotel: HotelUnitOfWork, room_id: UUID) -> Room:
    return await hotel.rooms.get(room_id)


async def list_rooms(hotel: HotelUnitOfWork, *, limit: int, offset: int) -> RoomPage:
    items = await hotel.rooms.list_page(limit=limit, offset=offset)
    return RoomPage(tuple(items), await hotel.rooms.count(), limit, offset)


async def update_room(hotel: HotelUnitOfWork, room_id: UUID, changes: RoomChanges) -> Room:
    room = await hotel.rooms.get(room_id)
    updated = replace(
        room,
        number=room.number if changes.number is UNSET else changes.number,
        capacity=room.capacity if changes.capacity is UNSET else changes.capacity,
        nightly_rate_cents=(
            room.nightly_rate_cents
            if changes.nightly_rate_cents is UNSET
            else changes.nightly_rate_cents
        ),
        notes=room.notes if changes.notes is UNSET else changes.notes,
    )
    await hotel.rooms.save(updated)
    await hotel.commit()
    return updated
