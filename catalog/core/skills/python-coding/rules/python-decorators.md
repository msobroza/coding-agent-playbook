---
id: python-decorators
name: Decorators
description: "Write decorators only for cross-cutting concerns, wrap with functools.wraps, type them with ParamSpec and TypeVar, and log through logging instead of print."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: functions
priority: 71
tags: [python, functions, decorators]
---

# Write typed decorators for cross-cutting concerns only

## Description

A decorator wraps a function to add behavior before, after or around it without changing the function. Reach for one for low-level concerns that apply the same way to many functions: logging, timing, metrics, authorization checks. For anything that is part of the business logic, compose functions and objects directly: an explicit call is easier to test and to follow than behavior hidden above a `def`.

Every decorator wraps with `functools.wraps(func)`, so the result keeps the original `__name__`, docstring and signature for introspection, logs and tracebacks. Type it with `ParamSpec` and `TypeVar` so callers keep their parameter and return types instead of `Callable[..., Any]`.

## Bad Example

```python
def log_calls(func: Callable[..., Any]) -> Callable[..., Any]:
    def wrapper(*args: Any, **kwargs: Any) -> Any:  # no wraps: __name__ is "wrapper"
        print(f"Calling {func.__name__}({args}, {kwargs})")
        result = func(*args, **kwargs)
        print(f"{func.__name__} returned {result}")
        return result

    return wrapper


@log_calls
def line_total(unit_price: Decimal, quantity: int) -> Decimal:
    return unit_price * quantity  # callers now see (...) -> Any
```

## Good Example

```python
logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def log_calls(func: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        logger.debug("calling %s args=%r kwargs=%r", func.__qualname__, args, kwargs)
        result = func(*args, **kwargs)
        logger.debug("%s returned %r", func.__qualname__, result)
        return result

    return wrapper


def timed(threshold_seconds: float) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                if elapsed > threshold_seconds:
                    logger.warning("%s took %.3fs", func.__qualname__, elapsed)

        return wrapper

    return decorator


@timed(threshold_seconds=0.5)
@log_calls
def line_total(unit_price: Decimal, quantity: int) -> Decimal:
    return unit_price * quantity
```

## Notes

- A decorator that takes configuration adds one outer level: `timed(threshold_seconds=0.5)` returns the decorator, which returns the wrapper.
- Stacked decorators apply bottom-up: the one nearest the `def` wraps the function first, so the example's `timed` measures the logged call. Past two or three, the order gets hard to reason about.
- Keep each decorator to one concern, and never swallow an exception inside the wrapper: let it propagate, or re-raise it after recording it.
- A decorator that keeps state between calls can be a class with `__call__` (call `functools.update_wrapper(self, func)` in `__init__`); for a single counter or flag, a closure with a `nonlocal` variable is enough.
- Logging uses `%`-style arguments, so the message is only built when the level is enabled.
- Decorator, partial or strategy: a concern applied uniformly to many functions is a decorator; behavior that varies per call is a strategy passed in (design-strategy in the design-patterns skill); configuration fixed at setup is `functools.partial` or a closure (`python-closures-and-partial`).
- Retrying a call is a decorator only under the retry rules in `python-retries-and-timeouts`.
