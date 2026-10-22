---
id: fastapi-dependency-providers
name: FastAPI dependency providers
description: "Build every per-request collaborator in a Depends provider declared once as an Annotated alias, and resolve the current user, tenant and paging in one provider each."
version: 1
scope: scoped
globs:
  - "**/main.py"
  - "**/app.py"
  - "**/asgi.py"
  - "**/deps.py"
  - "**/dependencies.py"
  - "**/routers/**/*.py"
  - "**/routes/**/*.py"
  - "**/api/**/*.py"
  - "**/endpoints/**/*.py"
  - "**/views.py"
  - "**/views/**/*.py"
applies_if:
  has_framework: ["fastapi"]
section: app-structure
priority: 45
tags: [python, fastapi]
---

# Build collaborators in dependency providers

## Description

When every session, client and repository comes from a provider, handlers stay thin and tests swap any collaborator without patching. Build per-request collaborators (database sessions, repositories, API clients) in provider functions injected with `Depends`; endpoint bodies never call `SessionLocal()` or instantiate an adapter. Write session providers as `yield` dependencies that close the session when the request ends, chain providers (session, then repository) so the wiring lives in one module, and declare each dependency once as an `Annotated` alias reused across routes. Resolve the current user, tenant or shared paging parameters in one provider each; a handler that uses the value declares it through the provider's alias.

## Bad Example

```python
@router.get("/rooms/{room_id}")
def read_room(room_id: int, request: Request) -> RoomRead:
    session = SessionLocal()  # wiring repeated in every endpoint, never closed
    rooms = SqlRoomRepository(session)
    token = request.headers["Authorization"].removeprefix("Bearer ")  # re-read per handler
    user = decode_user(token)
    return RoomRead.model_validate(rooms.get_owned(room_id, owner_id=user.id))
```

## Good Example

```python
# app/deps.py: the one provider module. RoomRepository is a Protocol the use
# cases consume; SqlRoomRepository and decode_user are the app's own code.
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session  # closed when the request ends


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_rooms(session: SessionDep) -> RoomRepository:
    return SqlRoomRepository(session)


RoomsDep = Annotated[RoomRepository, Depends(get_rooms)]


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    return await decode_user(token)  # raises HTTPException(401) on a bad token


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admins only")


@dataclass(frozen=True)
class Paging:
    limit: int
    cursor: int | None


def get_paging(
    limit: Annotated[int, Query(ge=1, le=100)] = 50, cursor: int | None = None
) -> Paging:
    return Paging(limit=limit, cursor=cursor)


PagingDep = Annotated[Paging, Depends(get_paging)]


# app/routers/admin_rooms.py
router = APIRouter(prefix="/admin/rooms", dependencies=[Depends(require_admin)])


@router.get("")
async def list_rooms(rooms: RoomsDep, paging: PagingDep) -> list[RoomRead]:
    found = await rooms.list(limit=paging.limit, after=paging.cursor)
    return [RoomRead.model_validate(room) for room in found]
```

## Notes

- FastAPI dependency aliases use concrete `AsyncSession` / `httpx.AsyncClient` at the route edge; Protocols are for the app's own ports.
- `APIRouter(dependencies=[...])` discards return values: attach there only providers run for their effect, such as an auth or role check that raises. Providers are cached per request, so one declared on the router and in a handler runs once.
- Express roles as providers (`require_admin` raising 403) and still scope data queries by owner or tenant. Take the tenant from the authenticated principal, never from a header or the body.
- Never re-read headers or tokens inside handler bodies.
- Prefer `Annotated[T, Depends(...)]` aliases to `param: T = Depends(...)` defaults: they are shorter, reused across routers, and give type checkers the real type.
- The stack-neutral composition root is the python-architecture skill's arch-composition-root rule, and ports are its arch-ports rule.
- Worked example: the hotel example's app/deps.py (the concrete `SessionDep`, the `HotelDep` port alias, clock and id providers).
- Which request step owns a change or a failure: open request-lifecycle.md.
