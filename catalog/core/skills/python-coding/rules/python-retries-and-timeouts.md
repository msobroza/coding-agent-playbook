---
id: python-retries-and-timeouts
name: Timeouts and retries
description: "Every outbound call gets an explicit timeout; idempotent calls get a small, bounded, transient-only retry."
version: 1
scope: scoped
globs:
  - "**/*.py"
applies_if:
  any_framework: ["requests", "httpx", "aiohttp"]
section: effects
priority: 53
tags: [python, network, resilience]
---

# Timeouts and bounded retries for outbound calls

## Description

Calls to external services fail intermittently: timeouts, rate limits, a node restarting. A call without a timeout can hang a worker indefinitely, and an unbounded or indiscriminate retry turns one failure into many and hides real errors.

- Every outbound HTTP, RPC or database call sets an explicit timeout taken from a named constant or the settings object: `timeout=` on each `requests` call, `httpx.Client(timeout=...)`, `aiohttp.ClientTimeout` on the session. Several client defaults wait forever.
- Wrap idempotent outbound calls in a retry with a small fixed attempt count (for example 3) and a short fixed delay. Never retry in a `while True` loop.
- Retry only transient failures, chosen by an explicit exception or status filter: connection errors, timeouts, 429, 502, 503, 504. After the last attempt, re-raise the original exception, not a generic wrapper, `None` or a silent fallback value.

## Bad Example

```python
def retry(fn: Callable[..., T], retries: int = 3, delay: float = 1.0, **kwargs: object) -> T:
    for attempt in range(retries):
        try:
            return fn(**kwargs)  # no timeout anywhere
        except Exception as e:  # retries bugs, auth failures and bad input alike
            if attempt == retries - 1:
                raise
            print(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
            time.sleep(delay)  # tests wait for real
    raise RuntimeError("Unreachable")
```

## Good Example

```python
RETRYABLE_STATUS: Final = frozenset({429, 502, 503, 504})


def is_transient(exc: httpx.HTTPError) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError))


def get_quote(client: httpx.Client, sku: str, sleep: Callable[[float], None]) -> Quote:
    for attempt in range(1, MAX_ATTEMPTS):
        try:
            return fetch_quote(client, sku)  # the client carries the timeout
        except httpx.HTTPError as exc:
            if not is_transient(exc):
                raise
            logger.warning(
                "quote fetch retry", extra={"attempt": attempt, "error": type(exc).__name__}
            )
        sleep(RETRY_DELAY_SECONDS)
    return fetch_quote(client, sku)  # last attempt: its error propagates unchanged
```

## Notes

- Never retry deterministic failures: `ValueError`, `TypeError` and validation errors, 401 and 403 and other 4xx responses, or business-rule failures such as insufficient funds. They fail the same way every time.
- Retried operations must be idempotent. Retry a non-idempotent write only after making it idempotent (an idempotency key the server deduplicates on, an upsert); otherwise don't retry it:

```python
def charge(gateway: Gateway, customer_id: CustomerId, amount: Decimal, key: str) -> None:
    gateway.charge(customer_id, amount, idempotency_key=key)  # a retry cannot charge twice
```

- Add exponential backoff, jitter, circuit breakers, rate limiting or fallbacks only when the project's agent instructions (CLAUDE.md, AGENTS.md) or the user ask for them.
- Keep the policy in the adapter that talks to the remote system, not in business code: a decorator built with `functools.wraps` and `ParamSpec` that catches only the transient types, or the project's existing retry library behind a thin wrapper the project owns.
- Inject the sleep function so tests count attempts without waiting; async code awaits `asyncio.sleep`, never `time.sleep`. Log each retry through `logging` with named fields (attempt, delay, error type), never `print`.
