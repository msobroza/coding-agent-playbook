---
id: python-context-managers
name: Context managers
description: "Bind every releasable resource to a with block; turn repeated try/finally into context managers that never swallow errors."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: effects
priority: 51
tags: [python, resources]
---

# Resource lifetime via context managers

A resource that is released only on the happy path leaks the first time something raises. Tie each resource's lifetime to a `with` block so release happens on every exit path.

## Acquire with `with`

- Files, DB connections and sessions, locks, sockets, HTTP clients and temporary directories are acquired with `with` or `async with`, never closed by hand after the work. Some drivers' own `with` ends the transaction, not the connection (`with sqlite3.connect(...)` commits or rolls back and leaves it open); wrap those in `contextlib.closing(...)`.
- A fixed set of resources goes in one parenthesized `with (open_a() as a, open_b() as b):`. When the count is known only at runtime, use `contextlib.ExitStack` or `AsyncExitStack`.
- Keep a read's block narrow: compute and raise domain errors after the resource is released. Inside a transaction or under a lock, check and raise inside the block, so the writes roll back and nothing changes between the check and the act.

## Extract repeated setup and teardown

- The second time the same acquire, `try`/`finally`, release shape appears, extract a context manager.
- Stateless: `@contextlib.contextmanager` (or `@asynccontextmanager`) with the `yield` inside `try`/`finally`, annotated `-> Iterator[T]` or `-> AsyncIterator[T]`. Configured or stateful: a class with `__enter__`/`__exit__`.
- Teardown must cope with partial setup, because acquisition itself can fail: guard handles that may never have been assigned.
- Don't wrap an operation that needs no cleanup in a context manager.

## Never swallow errors

- `__exit__` never returns `True` to hide an exception. When ignoring one specific error is the intent, write `contextlib.suppress(SpecificError)`.
- A transaction commits only after the block succeeds. On any other exit, an exception or an interrupt, it rolls back in `finally` and lets the exception propagate. Never commit in `finally`.
- Restore temporarily changed global state (working directory, environment variables, a patched attribute) in `finally`, so a failure inside the block cannot leave it changed.

```python
@contextmanager
def transaction(conn: Connection) -> Iterator[Connection]:
    committed = False
    try:
        yield conn
        conn.commit()
        committed = True
    finally:
        if not committed:  # an error or an interrupt: undo, then let it propagate
            conn.rollback()
```
