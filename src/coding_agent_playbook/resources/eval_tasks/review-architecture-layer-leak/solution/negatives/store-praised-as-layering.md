## Layer map

- Transport: `shop/api.py`
- Business: `shop/orders.py`
- Persistence: `shop/storage.py`
- Shared models: `shop/models.py`
- Entry point: `shop/main.py`

## Dependency flows

- `shop/main.py -> shop/api.py`: ok
- `shop/api.py -> shop/orders.py`: ok
- `shop/orders.py -> shop/storage.py`: ok (business calls down into persistence)
- `shop/storage.py -> shop/orders.py` (`shop/storage.py:17`, function-local): violation: persistence calls business code
- Every module -> `shop/models.py`: ok (the `shop/api.py:11` import sits under `if TYPE_CHECKING:`)

## Cycles

- `shop/orders.py -> shop/storage.py -> shop/orders.py`. The import inside `SqliteOrderStore.save` only defers the cycle to call time.

## What works well

- `shop/orders.py:21` keeps SQL out of the business rules by delegating persistence to `SqliteOrderStore`.
- `shop/models.py:6-17` keeps `LineItem` and `Order` as frozen dataclasses with no I/O.

## Findings

### Critical

1. `shop/storage.py:17` with `shop/orders.py:6`: import cycle between `shop.orders` and `shop.storage`. Principle: dependencies point one way. Cost: hoisting the local import breaks both modules. Minimal fix: move the total onto `Order` in `shop/models.py` so storage depends only on models.

### Suggestion

2. `shop/main.py:9-12`: the entry point could read the database path from the environment.

## Fix plan

1. Move `order_total` onto `Order` as a `total_cents` property and use it in `shop/storage.py` (touches `shop/models.py`, `shop/storage.py`, `shop/orders.py`).

No files were modified; this review only reports.
