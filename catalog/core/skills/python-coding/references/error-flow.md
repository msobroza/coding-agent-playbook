# Error flow

Where a failure is raised, wrapped, cleaned up, translated, logged and retried on its way out of the code, and the rule that owns each step. This page only routes: the rules hold the examples and the reasons.

## The path of one failure

1. Detect and raise: the code that finds the problem raises a domain error derived from the project's base exception, carrying the offending value (python-custom-exceptions).
2. Wrap: where a library or driver error leaves the code that called it, raise the domain error `from exc` so the cause stays in the traceback (python-error-boundaries, python-error-handling).
3. Pass through: every function in between lets the error propagate; no `try` without a concrete recovery (python-error-handling).
4. Clean up: resources and transactions are bound to `with` blocks, so they are released on the way out (python-context-managers, python-custom-context-managers).
5. Translate once: an entry point (a CLI `main`, a worker loop, a per-item batch loop, an HTTP handler) maps the domain error to its own outcome (python-error-boundaries).
6. Log once, with the traceback, at that entry point (python-error-handling).

## Raising

| Situation | Rule |
| --- | --- |
| A domain failure, or a broken argument contract | python-custom-exceptions |
| A precondition that fails before the main logic | python-early-return |
| An invalid dataclass field | python-dataclass-post-init |
| Invalid untrusted input | pydantic-boundaries |
| A `match` case nobody wrote | python-match-fallback |
| A required key that is missing | python-optional-keys |
| A failure reported as `None`, `False`, `-1` or an error dict | python-error-boundaries |

## Catching and translating

- Catch the narrowest type you can recover from; catch `Exception` only to clean up and re-raise; never use `assert` as a runtime check (python-error-handling).
- A `KeyError`, `IndexError` or driver error about to cross a layer, the CLI `main`, worker and per-item loops, and documented fallbacks (python-error-boundaries).
- A `ValidationError` where untrusted data enters (pydantic-boundaries).
- HTTP handlers, when the repository uses FastAPI: fastapi-error-boundaries in the web-application skill.

## Cleaning up

- Resources and transactions: `with` and `async with`, committing only after the block succeeds (python-context-managers).
- The same `try`/`finally` written twice: extract a context manager (python-custom-context-managers).
- Cancellation always propagates: release in `finally` and let `asyncio.CancelledError` through (python-async, python-error-handling).

## Concurrent failures

- Several awaited tasks fail: python-async; on Python 3.11 and later the failures arrive as an `ExceptionGroup` handled with `except*` (python-version-idioms.md).
- Some results are useful even when others fail: inspect every result (python-async).
- A background task fails after the code that started it returned: give it an owner that reports the failure (python-async-tasks).

## Retrying

- Transient failures of outbound calls, when the repository uses requests, httpx or aiohttp: a small, bounded, transient-only retry with a timeout (python-retries-and-timeouts).
- A retry written as a decorator (python-decorators, python-retries-and-timeouts).
- Writes that are not idempotent: make them idempotent first, or do not retry them (python-retries-and-timeouts).

## Smell and the rule that fixes it

| Smell | Rule |
| --- | --- |
| `except: pass`, or `except Exception` returning a default | python-error-handling |
| `raise` inside `except` without `from` | python-error-handling |
| `logger.error(str(exc))` instead of `logger.exception` | python-error-handling |
| `raise Exception(...)` or `ValueError` for a domain failure | python-custom-exceptions |
| `try`/`except` in every business function | python-error-boundaries |
| A `while True` retry loop, or a retry that catches everything | python-retries-and-timeouts |
| A `create_task` whose result is discarded | python-async-tasks |
| A swallowed `asyncio.CancelledError` | python-async |

Related guides: python-version-idioms.md, choosing-a-data-shape.md.
