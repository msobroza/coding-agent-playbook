---
id: python-async-generators
name: Async generators
description: "Stream paged or chunked async results with an async generator typed AsyncIterator[T], consumed with async for, instead of collecting everything first."
version: 1
scope: scoped
globs:
  - "**/*.py"
applies_if:
  python_version: ">=3.10"
section: async
priority: 58
tags: [python, async, streaming]
---

# Stream with async generators

## Description

An `async def` that contains `yield` is an async generator: it produces values one at a time and can await between them. Use one to stream paged API results, database rows or file chunks, so the consumer handles the first page while the next is still loading and memory holds one page, not all of them.

- Annotate it `-> AsyncIterator[T]` and yield typed records, not dicts.
- Consume it with `async for`, or with an async comprehension: `[item async for item in source]`.
- When the consumer may stop early, wrap the generator in `contextlib.aclosing(...)` so its cleanup runs at once.

## Bad Example

```python
async def fetch_all_orders(client: OrdersClient) -> list[Order]:
    orders: list[Order] = []
    cursor: str | None = None
    while True:
        page = await client.orders_page(cursor=cursor, limit=PAGE_SIZE)
        orders.extend(page.items)  # every page sits in memory before the first is used
        if page.next_cursor is None:
            return orders
        cursor = page.next_cursor
```

## Good Example

```python
@dataclass(frozen=True)
class OrderPage:
    items: tuple[Order, ...]
    next_cursor: str | None


async def iter_order_pages(client: OrdersClient) -> AsyncIterator[OrderPage]:
    cursor: str | None = None
    while True:
        page = await client.orders_page(cursor=cursor, limit=PAGE_SIZE)
        yield page
        if page.next_cursor is None:
            return
        cursor = page.next_cursor


async def export_orders(client: OrdersClient, sink: OrderSink) -> None:
    async for page in iter_order_pages(client):
        await sink.write(page.items)


async def first_overdue(client: OrdersClient) -> Order | None:
    async with aclosing(iter_order_pages(client)) as pages:
        async for page in pages:
            overdue = next((order for order in page.items if order.is_overdue), None)
            if overdue is not None:
                return overdue  # aclosing closes the generator here
    return None
```

## Notes

- Without `aclosing`, a generator abandoned mid-loop runs its `finally` and `async with` exits only when the loop gets round to closing it, so a connection it holds stays open. `contextlib.aclosing` exists from Python 3.10.
- Collect into a list only when the caller needs the whole result at once: `[order async for page in iter_order_pages(client) for order in page.items]`.
- Each page request keeps its own timeout (`python-retries-and-timeouts`, when the repo uses requests, httpx or aiohttp).
- Use `AsyncGenerator[T, None]` instead of `AsyncIterator[T]` only when callers use `asend` or `athrow`.
- A plain `for` loop cannot consume an async generator, and a sync generator cannot await; pick the async form only when producing a value needs an await.
