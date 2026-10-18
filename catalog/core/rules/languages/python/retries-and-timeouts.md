---
id: python-retries-and-timeouts
name: Timeouts and retries
description: "Every outbound call gets an explicit timeout; idempotent calls get a small, bounded, transient-only retry."
version: 1
scope: scoped
skill: python-coding
globs:
  - "**/*.py"
applies_if:
  any_framework: ["requests", "httpx", "aiohttp"]
priority: 57
tags: [python, network, resilience]
---

# Timeouts and bounded retries for outbound calls

A call without a timeout can hang a worker indefinitely, and an unbounded or indiscriminate retry turns one failure into many. Every outbound call gets a timeout; idempotent calls also get a small retry for transient failures only.

## Timeouts

Every outbound HTTP, RPC or database call sets an explicit timeout taken from a named constant or the settings object: `timeout=` on each `requests` call, `httpx.Client(timeout=...)`, `aiohttp.ClientTimeout` on the session. Several client defaults wait forever.

## Retries: bounded, transient-only, idempotent-only

- By default, wrap idempotent outbound calls in a retry with a small fixed attempt count (for example 3) and a short fixed delay. Never retry in a `while True` loop.
- Retry only transient failures, chosen by an explicit exception or status filter: connection errors, timeouts, 429, 502, 503, 504. Never retry on a bare `Exception`, other 4xx responses, or validation, authentication and business-rule errors.
- Retry a non-idempotent write only after making it idempotent (an idempotency key, an upsert); otherwise don't retry it.
- After the last attempt, re-raise the original exception, not a generic wrapper, `None` or a silent fallback value.
- Add exponential backoff, jitter, circuit breakers, rate limiting or fallbacks only when the project's agent instructions (CLAUDE.md, AGENTS.md) or the user ask for them.

## Where the policy lives

- Keep retry logic in the adapter that talks to the remote system, not in business code: a decorator built with `functools.wraps` and `ParamSpec`, or the project's existing retry library behind a thin wrapper the project owns.
- Inject the sleep function so tests count attempts without waiting; async code awaits `asyncio.sleep`, never `time.sleep`. Log each retry through `logging` with named fields (attempt, delay, error type), never `print`.

```python
def is_transient(exc: httpx.HTTPError) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS  # {429, 502, 503, 504}
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError))


def get_quote(client: httpx.Client, sku: str, sleep: Callable[[float], None]) -> Quote:
    for _ in range(MAX_ATTEMPTS - 1):
        try:
            return fetch_quote(client, sku)  # calls raise_for_status()
        except httpx.HTTPError as exc:
            if not is_transient(exc):
                raise
        sleep(RETRY_DELAY_SECONDS)
    return fetch_quote(client, sku)  # last attempt: its error propagates unchanged
```
