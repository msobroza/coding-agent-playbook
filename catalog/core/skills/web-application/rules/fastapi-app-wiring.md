---
id: fastapi-app-wiring
name: FastAPI app wiring
description: "Build the FastAPI app in a create_app(settings) factory, acquire long-lived resources in its lifespan and release them after yield, and let only the ASGI entrypoint read the environment."
version: 2
scope: scoped
globs:
  - "**/main.py"
  - "**/app.py"
  - "**/asgi.py"
  - "**/deps.py"
  - "**/dependencies.py"
  - "**/settings.py"
  - "**/config.py"
applies_if:
  has_framework: ["fastapi"]
section: app-structure
priority: 44
tags: [python, fastapi]
---

# Build the app in a factory and manage resources in its lifespan

## Description

In a FastAPI app the factory and its dependency system are the composition root. A module-level `engine = create_async_engine(...)`, `client = httpx.AsyncClient()` and `app = FastAPI()` mean that importing a module reads the environment and opens resources, every test shares one global app, and clients are never closed. Build the app in `create_app(settings)`. Create long-lived resources (the database engine, HTTP client pools, loaded models) in an async context manager passed as `FastAPI(lifespan=...)` and release them after its `yield`; never use the deprecated `@app.on_event`. Hand them to routes through a provider that reads `request.app.state`, never through module globals. Only the ASGI entrypoint calls the factory and reads the environment.

## Bad Example

```python
# app/main.py: reads the environment and builds a pool at import time
engine = create_async_engine(os.environ["DATABASE_URL"])
http_client = httpx.AsyncClient()  # never closed

app = FastAPI()


@app.on_event("startup")  # deprecated
async def startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

## Good Example

```python
# app/main.py
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.routers import invoices, users
from app.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    async with AsyncExitStack() as stack:  # releases in reverse order, even on errors
        engine = create_async_engine(settings.database_url.get_secret_value())
        stack.push_async_callback(engine.dispose)
        app.state.payments_client = await stack.enter_async_context(
            httpx.AsyncClient(
                base_url=settings.payments_base_url,
                timeout=httpx.Timeout(settings.payments_timeout_s),
            )
        )
        app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        yield


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.state.settings = settings
    app.include_router(users.router)
    app.include_router(invoices.router)
    return app


# app/deps.py
def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings)]
```

```python
# app/asgi.py: the only module that reads the environment
from app.main import create_app
from app.settings import Settings

app = create_app(Settings())  # a ValidationError lists every missing or invalid field
```

## Notes

- Web apps build the DB engine in the app factory or lifespan; scripts and CLIs may still build it at import time.
- The settings class itself, and the ban on a module-level `settings = Settings()`, are the python-coding skill's pydantic-typed-settings rule. A cached `get_settings()` works with overrides, but its instance can be imported from anywhere; constructing settings once in the entrypoint keeps them injected.
- Serve a cheap, unauthenticated `/health` liveness route. Deeper checks (database, upstream services) go to a separate readiness route that reports background warm-up without waiting on it.
- `contextlib.AsyncExitStack` keeps the lifespan flat however many resources it holds; the lifespan reads the settings `create_app` stored on `app.state`.
- The lifespan runs once per worker process: with four workers, each process has its own engine and pool.
- Keep `Base.metadata.create_all` out of startup; the schema is `alembic-migrations`'.
- Tests build `Settings(...)` with test values and pass it to `create_app`, with no environment patching (see `fastapi-dependency-overrides`).
- The factory only calls `include_router`; router prefixes and tags are `web-api-resource-naming`'s. Providers are `fastapi-dependency-providers`', and `async def` versus `def` is `fastapi-no-blocking-calls`'.
- Worked example: the hotel example's app/main.py (`create_app(settings)`, the lifespan, the error table) and app/asgi.py.
