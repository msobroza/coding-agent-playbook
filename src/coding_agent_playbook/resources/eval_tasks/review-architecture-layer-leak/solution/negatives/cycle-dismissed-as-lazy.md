## Layer map

- Transport: `shop/api.py`
- Business: `shop/orders.py`
- Persistence: `shop/storage.py`
- Shared models: `shop/models.py`
- Composition root: `shop/main.py`, which builds nothing today

## Dependency flows

- `shop/main.py -> shop/api.py`: ok
- `shop/api.py -> shop/orders.py`: ok
- `shop/orders.py -> shop/storage.py` (`shop/orders.py:6`): violation: business depends on a concrete persistence class
- `shop/storage.py -> shop/orders.py` (`shop/storage.py:17`): violation: persistence calls business code
- Every module -> `shop/models.py`: ok

## Cycles

None found: the import at `shop/storage.py:17` runs inside `save`, so the modules load without a cycle.

## What works well

- `shop/models.py:6-17` keeps the value types frozen and free of I/O.
- `shop/orders.py:16-19` rejects empty and oversized orders before persisting.

## Findings

### Critical

1. `shop/orders.py:21`: `place_order` constructs `SqliteOrderStore("orders.db")` itself. Principle: depend on abstractions and build concrete objects in one composition root. Cost: business logic cannot run without a real SQLite file. Minimal fix: take an `OrderStore` protocol parameter and build the store in `shop/main.py`.

### Suggestion

2. `shop/storage.py:17`: the function-local import of `order_total` is unusual; a comment explaining it would help.

## Fix plan

1. Add an `OrderStore` protocol to `shop/orders.py`, take it as a parameter, and build `SqliteOrderStore` in `shop/main.py` (touches `shop/orders.py`, `shop/api.py`, `shop/main.py`).

No files were modified; this review only reports.
