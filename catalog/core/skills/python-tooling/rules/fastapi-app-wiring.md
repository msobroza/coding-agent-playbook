---
id: fastapi-app-wiring
name: FastAPI app wiring
description: "Build collaborators in Depends providers and lifespan resources, use async def only for async I/O, and override dependencies in tests."
version: 1
scope: scoped
globs:
  - "**/routers/**/*.py"
  - "**/routes/**/*.py"
  - "**/api/**/*.py"
  - "**/main.py"
  - "**/app.py"
  - "**/dependencies.py"
  - "**/deps.py"
  - "tests/**/*.py"
applies_if:
  has_framework: ["fastapi"]
priority: 60
tags: [python, fastapi]
---

# FastAPI app wiring

In a FastAPI app the dependency system is the composition root. When every session, client and repository comes from a provider, handlers stay thin and tests swap any collaborator without patching.

## Providers

- Build per-request collaborators (database sessions, repositories, API clients) in provider functions injected with `Depends`. Endpoint bodies never call `SessionLocal()` or instantiate an adapter.
- Declare each dependency once as an `Annotated` alias typed as the Protocol the operation consumes, e.g. `Rooms = Annotated[RoomRepository, Depends(get_rooms)]`, and reuse the alias across routes.
- Write session providers as `yield` dependencies that close the session in `finally` (or yield inside `with Session(engine)`). Chain providers (session, then repository) so the wiring lives in one module.

## Lifespan

- Create long-lived resources (HTTP client pools, loaded models) in an async context manager passed as `FastAPI(lifespan=...)` and release them after its `yield`. Never use `@app.on_event`.
- Hand them to routes through a provider that reads `request.app.state` (or the lifespan state), not through module globals.

## Cross-cutting request concerns

- Resolve the current user, tenant or shared pagination parameters in one provider each. A handler that uses the value declares it through the provider's `Annotated` alias.
- `APIRouter(dependencies=[...])` discards return values: attach only providers run for their effect there, such as an auth check that raises. A provider declared in both places still runs once per request.
- Never re-read headers or tokens inside handler bodies.

## async def or def

- Use `async def` only when the handler or dependency awaits async I/O. Use plain `def` for sync libraries and CPU work: FastAPI runs those in a threadpool.
- Never call a blocking client, `time.sleep` or `thread.join()` inside an `async def` route or dependency; it stalls every in-flight request on the event loop. Expose background warm-up through a non-blocking readiness check instead of waiting on it.
- `asyncio.run()` inside an `async def` raises `RuntimeError` because a loop is already running; await the coroutine instead.

## Tests

- Set `app.dependency_overrides[get_rooms] = lambda: FakeRoomRepository()` inside a fixture and call `app.dependency_overrides.clear()` on teardown. Never assign overrides at import time, where they leak into every other test.
