---
id: python-async
name: Asyncio
description: "Start independent awaits together, give every task an owner, bound fan-out and total wait, and never block the event loop."
version: 1
scope: scoped
globs:
  - "**/*.py"
applies_if:
  python_version: ">=3.11"
priority: 53
tags: [python, async, concurrency]
---

# Python asyncio

An `async def` pays off only when the operations it waits on overlap, and it stalls every other task on the loop when it blocks. Keep concurrency explicit, bounded and cancellable.

## Run independent awaits together

- Awaiting calls one after another runs them in sequence. When they do not depend on each other, start them together.
- Use `asyncio.TaskGroup` when you need every result: the first failure cancels the remaining tasks and the group raises an `ExceptionGroup`. Handle it with `except*` clauses that name the types you can recover from.
- Use `asyncio.gather(..., return_exceptions=True)` only when partial results are useful. Then inspect every result: re-raise an `asyncio.CancelledError`, and handle each other exception at the per-item boundary, logging it with `exc_info` (`python-error-handling`).

```python
async def load_account_summary(client: BillingClient, customer_id: str) -> AccountSummary:
    async with asyncio.timeout(SUMMARY_TIMEOUT_SECONDS):
        async with asyncio.TaskGroup() as group:
            invoices = group.create_task(client.invoices(customer_id))
            limit = group.create_task(client.credit_limit(customer_id))
    return AccountSummary(invoices=invoices.result(), credit_limit=limit.result())
```

## Every task has an owner

- Never call `asyncio.create_task(...)` and throw the result away. The event loop holds only a weak reference, so the task can disappear before it finishes, and nobody ever sees its exception.
- Start a task inside a `TaskGroup`, or hand it to a supervisor object that the composition root builds and closes (`python-dependency-injection`). The supervisor keeps a reference until the task is done, reads the outcome in a done callback, and reports a failure there.
- Never collect tasks in a module-level set.

```python
class BackgroundJobs:
    def __init__(self, log: logging.Logger) -> None:
        self._log = log
        self._running: set[asyncio.Task[None]] = set()

    def start(self, job: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(job)
        self._running.add(task)
        task.add_done_callback(self._settle)

    def _settle(self, task: asyncio.Task[None]) -> None:
        self._running.discard(task)
        if not task.cancelled() and (error := task.exception()) is not None:
            self._log.error("background job failed", exc_info=error)

    async def aclose(self) -> None:
        for task in self._running:
            task.cancel()
        await asyncio.gather(*self._running, return_exceptions=True)
```

## Bound the fan-out

- Cap concurrent calls with an `asyncio.Semaphore`, created on the loop that uses it: inside the coroutine that fans out, or in a client built on that loop, never at import time.
- Size it from the remote service's stated limit, read from settings.
- When the HTTP client has its own connection limit, set that instead.

```python
async def quote_parcels(carrier: CarrierClient, parcels: Sequence[Parcel]) -> list[Quote]:
    slots = asyncio.Semaphore(carrier.max_parallel_requests)

    async def quote(parcel: Parcel) -> Quote:
        async with slots:
            return await carrier.quote(parcel)

    async with asyncio.TaskGroup() as group:
        pending = [group.create_task(quote(parcel)) for parcel in parcels]
    return [task.result() for task in pending]
```

## Bound the wait

Give a group of awaits one deadline with `async with asyncio.timeout(<setting>)`, as in the account summary above. The timeout on each single outbound call belongs to `python-retries-and-timeouts`, when the repo uses requests, httpx or aiohttp.

## Keep the loop free

- Inside `async def`, never call `time.sleep`, a blocking HTTP client, a blocking file read or a CPU-heavy loop: each one freezes every other task on the loop.
- Move blocking I/O off the loop with `await asyncio.to_thread(...)`, and CPU-bound work to a process pool.
- Acquire async resources with `async with` (`python-context-managers`).

## Cancellation passes through

Never swallow `asyncio.CancelledError`: a task that catches it and carries on cannot be stopped. Release what you hold in `finally`, then let the cancellation propagate.
