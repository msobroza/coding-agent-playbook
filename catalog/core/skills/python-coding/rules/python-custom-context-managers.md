---
id: python-custom-context-managers
name: Custom context managers
description: "Turn a repeated acquire, try/finally, release shape into a context manager whose teardown copes with partial setup and never swallows errors."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: effects
priority: 54
tags: [python, resources]
---

# Extract repeated setup and teardown into a context manager

## Description

The second time the same acquire, `try`/`finally`, release shape appears, extract a context manager. Cleanup is then written once, lives next to its setup, and composes with other `with` blocks, while each caller keeps only its business logic.

- Stateless: `@contextlib.contextmanager` (or `@asynccontextmanager`) with the `yield` inside `try`/`finally`, annotated `-> Iterator[T]` or `-> AsyncIterator[T]`. Everything before `yield` is setup, the yielded value is what `as` binds, and the `finally` is teardown.
- Configured or stateful: a class with `__enter__`/`__exit__` (or `__aenter__`/`__aexit__`).
- Teardown must cope with partial setup, because acquisition itself can fail: guard handles that may never have been assigned.

## Bad Example

```python
def fetch_blog(blog_id: str) -> Blog:
    connection = sqlite3.connect(DB_PATH)
    try:
        row = connection.execute("SELECT * FROM blogs WHERE id = ?", (blog_id,)).fetchone()
    finally:
        connection.close()
    return to_blog(blog_id, row)


def fetch_author(author_id: str) -> Author:  # the same shape, copied
    connection = sqlite3.connect(DB_PATH)
    try:
        row = connection.execute("SELECT * FROM authors WHERE id = ?", (author_id,)).fetchone()
    finally:
        connection.close()
    return to_author(author_id, row)


class Workspace:
    def __enter__(self) -> "Workspace":
        self.scratch = tempfile.TemporaryDirectory()
        self.connection = sqlite3.connect(self.db_path)  # if this raises, __exit__ never
        return self  # runs and the scratch directory leaks
```

## Good Example

```python
@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path)
    try:
        yield connection
    finally:
        connection.close()


def fetch_blog(blog_id: str) -> Blog:
    with connect(DB_PATH) as connection:
        row = connection.execute("SELECT * FROM blogs WHERE id = ?", (blog_id,)).fetchone()
    return to_blog(blog_id, row)


class Workspace:  # configured and stateful, so a class
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._resources = ExitStack()

    def __enter__(self) -> "Workspace":
        with ExitStack() as stack:  # a failed step releases the steps before it
            self.scratch = stack.enter_context(tempfile.TemporaryDirectory())
            self.connection = stack.enter_context(closing(sqlite3.connect(self._db_path)))
            self._resources = stack.pop_all()  # every step succeeded: keep them open
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._resources.close()
```

## Notes

- `__exit__` returns `None`, so the exception propagates (why it never returns `True` is in `python-context-managers`). The async forms follow the same rules with `async with` and an `await` in the `finally`.
- A manager for a temporary state change (the restore-in-`finally` rule is in `python-context-managers`) saves `original = getattr(obj, attr)`, calls `setattr(...)`, then yields inside `try`/`finally` and restores `original` in the `finally`.
- A timing manager records `time.perf_counter()` before the `yield` and logs the elapsed time through `logging` in the `finally`, never with `print`.
- A manager does not commit a transaction for its caller; the commit-only-on-success transaction is in `python-context-managers`.
- A `try`/`finally` written only to release a resource becomes a `with` block, on the resource's own context manager or an extracted one.
- Don't wrap an operation that needs no cleanup in a context manager.
