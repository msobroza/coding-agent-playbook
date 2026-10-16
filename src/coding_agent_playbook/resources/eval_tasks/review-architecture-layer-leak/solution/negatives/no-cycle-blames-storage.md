## Layer map

- Transport: `shop/api.py`
- Business: `shop/orders.py`
- Persistence: `shop/storage.py`
- Shared models: `shop/models.py`
- Entry point: `shop/main.py`

## Dependency flows

- `shop/main.py -> shop/api.py`: ok
- `shop/api.py -> shop/orders.py`: ok
- `shop/orders.py -> shop/storage.py`: ok
- `shop/storage.py -> shop/orders.py`: ok (function-local import, loaded lazily)
- `shop/api.py -> shop/models.py` (`shop/api.py:11`): violation: transport reaches into the model layer

## Cycles

none found

## What works well

- `shop/models.py:6-17` keeps the value types frozen and free of I/O.
- `shop/orders.py:16-19` validates the order before anything is stored.

## Findings

### Critical

1. `shop/storage.py:10`: `SqliteOrderStore` opens its connection in `__init__` and never closes it. Principle: own resource lifetimes explicitly. Cost: every call leaks a connection. Fix: add `close()` and use the store as a context manager.

### Important

2. `shop/api.py:11`: the `Order` import ties the transport layer to the model module. Fix: return plain dicts from the business layer instead.

## Fix plan

1. Give `shop/storage.py` a `close()` and a context-manager lifecycle.
2. Drop the `Order` import from `shop/api.py`.

No files were modified; this review only reports.
