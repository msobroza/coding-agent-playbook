---
id: sqlalchemy-session-per-request
name: Session per request
description: "Create the engine once in the lifespan and hand out one AsyncSession per request through a yield dependency."
scope: scoped
globs:
  - "**/main.py"
  - "**/app.py"
  - "**/asgi.py"
  - "**/deps.py"
  - "**/dependencies.py"
  - "**/models.py"
  - "**/models/**/*.py"
  - "**/db/**/*.py"
  - "**/database.py"
  - "**/repositories/**/*.py"
applies_if:
  has_framework: ["fastapi"]
  any_dependency: ["sqlalchemy", "alembic"]
section: database
priority: 26
tags: [python, fastapi, sqlalchemy, database]
---

# Create the engine once and a session per request

## Description

The engine owns the connection pool and should exist once per process: create it in the lifespan and dispose of it on shutdown. A `Session` is a unit of work with its own identity map and transaction and must not be shared between concurrent requests. A module-level session mixes requests' transactions; an engine created per request opens a new pool every time. Hand out sessions through a yield dependency that opens a fresh one per request and always closes it.

## Bad Example

```python
import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

engine = create_async_engine(os.environ["DATABASE_URL"])  # created at import time
session = AsyncSession(engine)  # one session shared by every request

router = APIRouter(prefix="/users")


@router.get("/{user_id}")
async def read_user(user_id: int) -> UserRead:
    user = await session.get(User, user_id)  # sees other requests' pending changes
    return UserRead.model_validate(user)
```

## Good Example

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_async_engine(
            settings.database_url.get_secret_value(), pool_pre_ping=True
        )  # one engine per process
        app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        yield
        await engine.dispose()

    return FastAPI(lifespan=lifespan)


# app/deps.py
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session  # closed after the request; uncommitted work is rolled back


SessionDep = Annotated[AsyncSession, Depends(get_session)]


# app/routers/users.py: NotFoundError is the project's domain error, UserRead the schema
@router.get("/{user_id}")
async def read_user(user_id: int, session: SessionDep) -> UserRead:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User", user_id)
    return UserRead.model_validate(user)
```

## Notes

- Web apps build the DB engine in the app factory or lifespan; scripts and CLIs may still build it at import time. Jobs, CLIs and workers follow python-architecture's sqlalchemy-engine-and-session-scope.
- FastAPI dependency aliases use concrete `AsyncSession` / `httpx.AsyncClient` at the route edge; Protocols are for the app's own ports.
- Use `expire_on_commit=False` with `AsyncSession`. Otherwise every attribute is expired on commit, and reading one afterwards needs implicit I/O, which fails with `MissingGreenlet` in async code.
- Never use one `AsyncSession` from concurrent tasks (`asyncio.gather` over the same session raises errors). Give each task its own session from the sessionmaker, or run the queries one after another.
- FastAPI caches dependencies per request, so the endpoint and sub-dependencies such as `get_current_user` share the same session. Chain providers (session, then repository) in one module.
- The dependency only opens and closes the session; committing belongs to the use case (`sqlalchemy-transaction-boundary`).
- Size the pool for the whole deployment: (`pool_size` + `max_overflow`) multiplied by the number of worker processes must stay below the database's connection limit.
- Background jobs and workers open their own `async with sessionmaker() as session:`; never keep using a request's session after the response.
- The hotel example shows this wiring: examples/fastapi-hotel-api/app/main.py builds the engine and sessionmaker in the lifespan, and examples/fastapi-hotel-api/app/deps.py holds `get_session`.
