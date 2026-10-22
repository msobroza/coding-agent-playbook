"""Room routes: parse the request, call one use case, convert the record it returns."""

from __future__ import annotations

from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response, status

from app.deps import HotelDep, NewIdDep
from app.operations import room as room_ops
from app.routers.schemas import RoomCreate, RoomPage, RoomPatch, RoomRead

router = APIRouter(prefix="/rooms", tags=["rooms"])

NOT_FOUND: Final[dict[int | str, dict[str, Any]]] = {404: {"description": "No room has this id"}}


@router.post("", status_code=status.HTTP_201_CREATED, summary="Add a room")
async def create_room(
    body: RoomCreate, hotel: HotelDep, new_id: NewIdDep, request: Request, response: Response
) -> RoomRead:
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


@router.get("", summary="List rooms by number, one page at a time")
async def list_rooms(
    hotel: HotelDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RoomPage:
    return RoomPage.model_validate(await room_ops.list_rooms(hotel, limit=limit, offset=offset))


@router.get("/{room_id}", summary="Read a room", responses=NOT_FOUND)
async def read_room(room_id: UUID, hotel: HotelDep) -> RoomRead:
    return RoomRead.model_validate(await room_ops.get_room(hotel, room_id))


@router.patch("/{room_id}", summary="Change some of a room's fields", responses=NOT_FOUND)
async def patch_room(room_id: UUID, body: RoomPatch, hotel: HotelDep) -> RoomRead:
    # The only dict on the request path: exclude_unset keeps "left out" apart from "null".
    changes = room_ops.RoomChanges(**body.model_dump(exclude_unset=True))
    return RoomRead.model_validate(await room_ops.update_room(hotel, room_id, changes))
