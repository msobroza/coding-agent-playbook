## Layer map

- Transport: `shop/api.py`
- Business: `shop/orders.py`
- Persistence: `shop/storage.py`
- Shared models: `shop/models.py`
- Composition root (entry point): `shop/main.py`, which builds nothing today

## Dependency flows

- `shop/main.py -> shop/api.py`: ok
- `shop/api.py -> shop/orders.py`: ok
- `shop/api.py -> shop/models.py`: ok (the `Order` import at `shop/api.py:11` sits under `if TYPE_CHECKING:`, so it has no runtime edge)
- `shop/orders.py -> shop/models.py`, `shop/storage.py -> shop/models.py`: ok
- `shop/orders.py -> shop/storage.py` (`shop/orders.py:6`): violation, business depends on a concrete persistence class
- `shop/storage.py -> shop/orders.py` (`shop/storage.py:17`, function-local): violation, persistence calls business code

## Cycles

- `shop/orders.py -> shop/storage.py -> shop/orders.py`. The import inside `SqliteOrderStore.save` only defers the circular import to call time; the cycle is still there.

## What works well

- `shop/models.py:6-17` keeps `LineItem` and `Order` as frozen dataclasses with no I/O, so every layer can share them safely.
- `shop/api.py:14-24` only translates payloads to and from domain types; the validation rules live in `place_order`.
- `shop/orders.py:16-19` raises on empty and oversized orders before anything is persisted.

## Findings

### Critical

1. `shop/orders.py:21`: `place_order` constructs `SqliteOrderStore("orders.db")` itself. Principle: depend on abstractions, and build concrete objects in one composition root. Cost: business logic cannot run without a real SQLite file in the current directory (the tests at `tests/test_orders.py:11` must `chdir` to work around it), the path cannot be configured, and the backend cannot be swapped. Minimal fix: let the business layer own a small protocol and receive the store as a parameter.

   Before:

   ```python
   store = SqliteOrderStore("orders.db")
   store.save(order)
   ```

   After:

   ```python
   class OrderStore(Protocol):
       def save(self, order: Order) -> None: ...


   def place_order(customer_id: str, items: list[LineItem], store: OrderStore) -> Order:
       ...
       store.save(order)
   ```

   `shop/main.py` builds `SqliteOrderStore(path)` once and passes it through `handle_place_order` (or binds it with `functools.partial`). Tests pass an in-memory fake.

2. `shop/storage.py:17` with `shop/orders.py:6`: import cycle between `shop.orders` and `shop.storage`. Persistence reaches up into business code for `order_total`, and the function-local import exists only to dodge the import-time failure. Principle: dependencies point one way. Cost: either module breaks as soon as someone hoists that import; the two modules cannot be understood or tested apart. Minimal fix: move the total next to the data it reads, so storage depends only on models.

   Before:

   ```python
   from shop.orders import order_total
   ... order_total(order)
   ```

   After:

   ```python
   # shop/models.py
   @property
   def total_cents(self) -> int:
       return sum(i.quantity * i.unit_price_cents for i in self.items)

   # shop/storage.py
   ... order.total_cents
   ```

### Important

3. `shop/main.py:9-12`: the entry point is not a composition root yet; it wires nothing, which is why construction leaked into `shop/orders.py:21`. Fix: build the store and any configuration (the database path) here, and pass them down.

### Suggestion

4. `shop/storage.py:10`: `SqliteOrderStore` opens its connection in `__init__` and never closes it. Once the store is built in `main.py`, give it a `close()` or context-manager lifecycle owned by the entry point.

## Fix plan

1. Move the total onto `Order` in `shop/models.py` and make `shop/storage.py` use it; this removes the cycle (touches `shop/models.py`, `shop/storage.py`, `shop/orders.py`).
2. Add an `OrderStore` protocol to `shop/orders.py` and make `place_order` take a `store` parameter; drop the `shop.storage` import from `shop/orders.py` (touches `shop/orders.py`, `shop/api.py`).
3. Build `SqliteOrderStore` in `shop/main.py` with a configurable path and pass it through `handle_place_order` (touches `shop/main.py`, `shop/api.py`).
4. Replace the `chdir` workaround in `tests/test_orders.py` with an in-memory fake store.

No files were modified; this review only reports.
