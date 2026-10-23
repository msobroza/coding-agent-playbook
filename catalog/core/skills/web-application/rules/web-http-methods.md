---
id: web-http-methods
name: HTTP methods and status codes
description: "Use each HTTP method for its meaning and answer with its success code: safe GET, POST 201 with Location, idempotent PUT, partial PATCH, DELETE 204."
version: 1
scope: scoped
globs:
  - "**/routers/**/*.py"
  - "**/routes/**/*.py"
  - "**/api/**/*.py"
  - "**/endpoints/**/*.py"
  - "**/views.py"
  - "**/views/**/*.py"
applies_if:
  any_framework: ["fastapi", "flask", "django", "starlette"]
section: api-design
priority: 43
tags: [python, web, api]
---

# Use each HTTP method for its meaning

## Description

Clients, caches and proxies act on the method and the status code before they read a body. A `GET` that changes state is repeated by prefetchers and retried by proxies; a create that answers `200` gives the client no way to find the new resource; a `PUT` used for a partial update silently nulls the fields the client left out. Give each method its meaning: `GET` reads with no side effects and can be cached, `POST` creates and answers `201` with a `Location` header, `PUT` replaces the whole resource and is idempotent, `PATCH` changes only the fields sent, and `DELETE` removes and answers `204` with no body.

## Bad Example

```python
router = APIRouter(prefix="/rooms")


@router.get("/{room_id}/archive")  # state change on a GET
async def archive_room(room_id: int, rooms: RoomsDep) -> RoomRead:
    return RoomRead.model_validate(await rooms.archive(room_id))


@router.post("")  # 200 and no Location for a created resource
async def create_room(body: RoomCreate, rooms: RoomsDep) -> RoomRead:
    return RoomRead.model_validate(await rooms.add(body))


@router.put("/{room_id}")  # a partial body: every field left out becomes None
async def update_room(room_id: int, body: RoomUpdate, rooms: RoomsDep) -> RoomRead:
    return RoomRead.model_validate(await rooms.replace(room_id, body.model_dump()))


@router.delete("/{room_id}")  # 200 with the deleted body
async def delete_room(room_id: int, rooms: RoomsDep) -> RoomRead:
    return RoomRead.model_validate(await rooms.remove(room_id))
```

## Good Example

```python
# RoomsDep is the app's Annotated alias for its room repository; RoomCreate,
# RoomUpdate and RoomRead are the room's request and response schemas.
router = APIRouter(prefix="/rooms")


@router.get("/{room_id}")
async def read_room(room_id: int, rooms: RoomsDep) -> RoomRead:
    return RoomRead.model_validate(await rooms.get(room_id))


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_room(body: RoomCreate, rooms: RoomsDep, response: Response) -> RoomRead:
    room = await rooms.add(body)
    response.headers["Location"] = f"/rooms/{room.id}"
    return RoomRead.model_validate(room)


@router.put("/{room_id}")  # full replacement: the body carries every field
async def replace_room(room_id: int, body: RoomCreate, rooms: RoomsDep) -> RoomRead:
    return RoomRead.model_validate(await rooms.replace(room_id, body.model_dump()))


@router.patch("/{room_id}")  # partial: only the fields the client sent
async def update_room(room_id: int, body: RoomUpdate, rooms: RoomsDep) -> RoomRead:
    changes = body.model_dump(exclude_unset=True)
    return RoomRead.model_validate(await rooms.update(room_id, changes))


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(room_id: int, rooms: RoomsDep) -> None:
    await rooms.remove(room_id)
```

## Notes

- Success codes: `200` for a read or an update that returns the resource, `201` for a create, `204` for a delete or any success without a body.
- A malformed or invalid body is FastAPI's own `422`; do not re-validate in the route to answer `400`. A duplicate create is `409`.
- A `500` is never returned on purpose: it means a bug or an outage. Failure codes and the one mapping that produces them are `fastapi-error-boundaries`'.
- Actions are not verbs in the path: model them as a sub-resource or a state field (`POST /rooms/{room_id}/archival`, or `PATCH` with `{"archived": true}`). URL shape is `web-api-resource-naming`'s.
- For a whole-API review before a release, open api-review-checklist.md.
