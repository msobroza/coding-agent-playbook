---
id: python-context-managers
name: Context managers
description: "Bind every releasable resource to a with or async with block, and commit a transaction only after its block succeeds."
scope: scoped
globs:
  - "**/*.py"
section: effects
priority: 51
tags: [python, resources]
---

# Resource management with `with` and `async with`

## Description

Files, DB connections and sessions, locks, sockets, HTTP clients and responses, and temporary directories are acquired with `with` or `async with`, never closed by hand after the work. A resource released only on the happy path leaks the first time something raises; a `with` block releases it on every exit path and keeps cleanup out of the business logic.

## Bad Example

```python
def fetch_users(db_path: Path) -> list[User]:
    connection = sqlite3.connect(db_path)
    rows = connection.execute("SELECT id, email FROM users").fetchall()  # if this raises...
    connection.close()  # ...this never runs
    return [User(*row) for row in rows]


async def fetch_report(url: str) -> Report:
    session = aiohttp.ClientSession()  # no timeout, and leaked on any error
    response = await session.get(url)
    payload = await response.json()
    await session.close()
    return Report.from_payload(payload)
```

## Good Example

```python
from contextlib import closing
from pathlib import Path


def fetch_users(db_path: Path) -> list[User]:
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute("SELECT id, email FROM users").fetchall()
    return [User(*row) for row in rows]  # compute after the resource is released


async def fetch_report(session: aiohttp.ClientSession, url: str) -> Report:
    async with session.get(url) as response:  # the caller owns the session
        response.raise_for_status()
        return Report.from_payload(await response.json())


async def main(settings: Settings) -> None:
    timeout = aiohttp.ClientTimeout(total=settings.http_timeout_seconds)
    async with (
        aiohttp.ClientSession(timeout=timeout) as session,
        open_pool(settings.database_dsn) as pool,
    ):
        await store_report(pool, await fetch_report(session, settings.report_url))
```

## Notes

- Some drivers' own `with` ends the transaction, not the connection (`with sqlite3.connect(...)` commits or rolls back and leaves it open); wrap those in `contextlib.closing(...)`.
- A fixed set of resources goes in one parenthesized `with (open_a() as a, open_b() as b):`, which needs Python 3.10. When the count is known only at runtime, use `contextlib.ExitStack` or `AsyncExitStack`; it exits them in reverse order.
- Keep a read's block narrow: compute and raise domain errors after the resource is released. Inside a transaction or under a lock, check and raise inside the block, so the writes roll back and nothing changes between the check and the act.
- `__exit__` never returns `True` to hide an exception. When ignoring one specific error is the intent, write `contextlib.suppress(SpecificError)`.
- A transaction commits only after the block succeeds. On any other exit, an exception or an interrupt, it rolls back in `finally` and lets the exception propagate; never commit in `finally`:

```python
@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    committed = False
    try:
        yield conn
        conn.commit()
        committed = True
    finally:
        if not committed:  # an error or an interrupt: undo, then let it propagate
            conn.rollback()
```

- Restore temporarily changed global state (working directory, environment variables, a patched attribute) in `finally`, so a failure inside the block cannot leave it changed.
- Writing a new context manager, with a class or `@contextmanager`, is `python-custom-context-managers`.
