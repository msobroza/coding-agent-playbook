---
id: fastapi-no-blocking-calls
name: No blocking calls in async routes
description: "Never block the event loop in async def routes and dependencies; use plain def for sync work and move blocking calls to a thread."
scope: scoped
globs:
  - "**/routers/**/*.py"
  - "**/routes/**/*.py"
  - "**/api/**/*.py"
  - "**/endpoints/**/*.py"
  - "**/views.py"
  - "**/views/**/*.py"
  - "**/main.py"
  - "**/app.py"
  - "**/asgi.py"
  - "**/deps.py"
  - "**/dependencies.py"
  - "**/services/**/*.py"
applies_if:
  has_framework: ["fastapi"]
section: async-io
priority: 31
tags: [python, fastapi, async]
---

# Never block the event loop in async def endpoints

## Description

FastAPI runs `async def` endpoints and dependencies on the event loop. A blocking call inside one, such as `requests.get`, `time.sleep`, `thread.join()`, a sync database driver, or CPU-heavy work like password hashing or PDF rendering, freezes the loop: every other request on that worker waits. Use `async def` only when the handler awaits async I/O, and inside it call awaitable libraries only; move unavoidable blocking or CPU-bound calls to a thread with `asyncio.to_thread`. When an endpoint calls nothing but blocking libraries or does CPU work, declare it with plain `def`; FastAPI runs those in a thread pool.

## Bad Example

```python
import time

import requests

router = APIRouter(prefix="/reports", dependencies=[Depends(get_current_user)])


@router.post("")
async def create_report(month: str, user: CurrentUser, session: SessionDep) -> Response:
    invoices = list(await session.scalars(select(Invoice).where(Invoice.owner_id == user.id)))
    rates = requests.get("https://fx.example.com/rates", timeout=5).json()  # blocks
    time.sleep(1)  # pauses every request on this worker, not just this one
    pdf = render_pdf(invoices, rates)  # seconds of CPU on the event loop
    return Response(pdf, media_type="application/pdf")
```

## Good Example

```python
import asyncio
from decimal import Decimal

import httpx
from fastapi import Response
from pydantic import BaseModel

# PaymentsClientDep is the shared httpx.AsyncClient alias, SettingsDep the settings
# alias; SessionDep, CurrentUser and Invoice are the per-request session, the
# authenticated user and the ORM model.
router = APIRouter(prefix="/reports", dependencies=[Depends(get_current_user)])


class FxRates(BaseModel):
    base: str
    rates: dict[str, Decimal]


# Awaits the shared client, translates httpx.HTTPError and validates the payload
# with FxRates.model_validate_json, as in httpx-shared-client.
async def fetch_fx_rates(client: httpx.AsyncClient) -> FxRates: ...
def render_pdf(invoices: list[Invoice], fx: FxRates) -> bytes: ...  # seconds of CPU


@router.post("")
async def create_report(
    month: str, user: CurrentUser, session: SessionDep, payments: PaymentsClientDep
) -> Response:
    invoices = list(await session.scalars(select(Invoice).where(Invoice.owner_id == user.id)))
    fx = await fetch_fx_rates(payments)  # awaited, non-blocking
    pdf = await asyncio.to_thread(render_pdf, invoices, fx)  # CPU work off the loop
    return Response(pdf, media_type="application/pdf")


# Only blocking calls inside: plain def runs in FastAPI's thread pool
@router.get("/{report_id}/archive")
def read_archived_report(report_id: int, settings: SettingsDep) -> Response:
    pdf = (settings.report_archive_dir / f"{report_id}.pdf").read_bytes()  # blocking is fine
    return Response(pdf, media_type="application/pdf")
```

## Notes

- Common blockers: `requests`, `urllib`, `boto3`, `psycopg2` or a sync `Session`, the sync `redis` client, `smtplib`, `time.sleep`, `subprocess.run`, file I/O on network storage, Argon2 or bcrypt, and pandas or Pillow processing.
- Async replacements: `httpx.AsyncClient`, `AsyncSession` with an async driver (asyncpg, psycopg 3, aiosqlite), `redis.asyncio`, `aiobotocore`; for file I/O, `asyncio.to_thread` or `anyio.Path`. A sync driver inside an async handler blocks the loop on every query.
- Never call `asyncio.run()` inside a route or dependency: FastAPI already runs the loop, so it raises `RuntimeError`. Await the coroutine instead.
- Threads help with blocking I/O and with C extensions that release the GIL. Pure-Python CPU work still holds the GIL; use a `ProcessPoolExecutor`. Jobs that take minutes belong in a worker: use the project's task queue, or propose one (Celery, arq, RQ), never add it unasked.
- Both thread pools are bounded: sync endpoints run in AnyIO's pool, and `asyncio.to_thread` uses the event loop's separate default executor. Many slow blocking calls can exhaust either.
- During development, `PYTHONASYNCIODEBUG=1` makes asyncio log callbacks that block for more than 100 ms.
- Decide per endpoint: inside `def`, do not call async functions; inside `async def`, do not call sync I/O. Forgotten awaits, fan-out and deadlines are python-coding's python-async.
