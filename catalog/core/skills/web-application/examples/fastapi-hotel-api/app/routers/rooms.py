"""Room routes: parse the request, call one use case, convert the record it returns."""

from __future__ import annotations

from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response, status

from app.deps import HotelDep, NewIdDep
from app.operations import room as room_ops
from app.routers.schemas import ResponseDocs, RoomCreate, RoomPageRead, RoomPatch, RoomRead

router = APIRouter(prefix="/rooms", tags=["rooms"])

ROOM_NOT_FOUND: Final[ResponseDocs] = {404: {"description": "No room has this id"}}
ROOM_REFUSED: Final[ResponseDocs] = {
    422: {"description": "A field is missing, out of range, or null where it cannot be cleared"}
}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Add a room",
    responses=ROOM_REFUSED,
)
async def create_room(
    body: RoomCreate, hotel: HotelDep, new_id: NewIdDep, request: Request, response: Response
) -> RoomRead:
    """Add a room and answer 201 with a Location header naming it.

    Example: ``POST /rooms {"number": "101", "capacity": 2, "nightly_rate_cents": 9500}``.
    """
    room = await room_ops.create_room(
        hotel,
        number=body.number,
        capacity=body.capacity,
        nightly_rate_cents=body.nightly_rate_cents,
        notes=body.notes,
        new_id=new_id,
    )
    response.headers["Location"] = request.url_for("read_room", room_id=room.room_id).path
    return RoomRead.model_validate(room)


@router.get("", summary="List rooms by number, one page at a time", responses=ROOM_REFUSED)
async def list_rooms(
    hotel: HotelDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RoomPageRead:
    """One page of rooms ordered by number, with the total count of rooms.

    Example: ``GET /rooms?limit=20&offset=40`` -> the third page of 20.
    """
    page = await room_ops.list_rooms(hotel, limit=limit, offset=offset)
    return RoomPageRead.model_validate(page)


@router.get("/{room_id}", summary="Read a room", responses={**ROOM_NOT_FOUND, **ROOM_REFUSED})
async def read_room(room_id: UUID, hotel: HotelDep) -> RoomRead:
    """The room ``room_id``, or 404.

    Example: ``GET /rooms/{room_id}`` -> 200 with the room.
    """
    return RoomRead.model_validate(await room_ops.get_room(hotel, room_id))


@router.patch(
    "/{room_id}",
    summary="Change some of a room's fields",
    responses={**ROOM_NOT_FOUND, **ROOM_REFUSED},
)
async def patch_room(room_id: UUID, body: RoomPatch, hotel: HotelDep) -> RoomRead:
    """Change only the fields the body sends; a null ``notes`` clears them.

    Example: ``PATCH /rooms/{room_id} {"notes": null}`` -> 200 with the notes cleared.
    """
    # The only dict on the request path: exclude_unset keeps "left out" apart from "null".
    changes = room_ops.RoomChanges(**body.model_dump(exclude_unset=True))
    return RoomRead.model_validate(await room_ops.update_room(hotel, room_id, changes))
