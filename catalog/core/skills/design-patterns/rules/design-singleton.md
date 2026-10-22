---
id: design-singleton
name: Singleton
description: "When one shared instance is needed, build it once in the entry point and pass it down instead of a class that caches its own instance; for costly reusable resources, use a bounded pool whose connections return through a context manager."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: specialized-patterns
priority: 90
tags: [python, design, patterns]
---

# Singleton

## Description

The class-based singleton comes from languages without module-level objects. In Python it is global state in disguise: functions use it without declaring it, tests cannot give each case its own instance, and every caller is tied to one implementation. When the process needs exactly one connection pool, client or cache, create it once in the entry point and pass it to the code that uses it. One instance in the composition root gives the same guarantee, visibly. The ban on metaclass caches, caching `__new__` and module-level locators, and the short list of acceptable process-wide objects, belong to `python-no-global-singletons`.

## Bad Example

```python
class RateCache:
    _instance: "RateCache | None" = None

    @classmethod
    def get_instance(cls) -> "RateCache":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


def price_in(order: Order, currency: Currency) -> Decimal:
    return order.total * RateCache.get_instance().rate(currency)  # hidden dependency
```

## Good Example

```python
def price_in(order: Order, currency: Currency, rates: RateCache) -> Decimal:
    return order.total * rates.rate(currency)


def main() -> None:
    rates = RateCache()  # the one instance, built here and passed down
    run_server(OrderService(rates=rates))
```

When creating each object is costly and more than one is needed, keep a bounded pool built from an injected factory; the context manager returns the object on every path:

```python
class ConnectionPool:
    def __init__(self, size: int, connect: Callable[[], Connection]) -> None:
        self._idle: Queue[Connection] = Queue(maxsize=size)
        for _ in range(size):
            self._idle.put(connect())

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        conn = self._idle.get()
        try:
            yield conn
        finally:
            self._idle.put(conn)


with pool.connection() as conn:
    conn.execute(query)
```

## Notes

- A module is imported once, so a module attribute is already a single object. Keep a module-level instance for stateless process-wide services such as a logger; one that holds state must be reset between tests.
- A library that already pools (a database engine, an HTTP client) needs no wrapper: build it once in the entry point and pass it down.
- Not when the object is cheap and holds no shared resource: create it where it is used.
- Passing the instance in is `python-dependency-injection`; where the entry point wires it is the python-architecture skill's composition root.
