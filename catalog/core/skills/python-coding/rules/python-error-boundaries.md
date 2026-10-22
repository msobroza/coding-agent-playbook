---
id: python-error-boundaries
name: Error boundaries
description: "Raise domain errors in the core and translate them once at entry points; never let sentinels, error dicts or a KeyError cross a layer."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: errors
priority: 22
tags: [python, errors]
---

# Translate errors once, at the boundary

## Description

Business code raises; only entry points catch. An HTTP handler or exception handler, a CLI `main`, a worker loop or a per-item batch loop is an isolation boundary: it maps domain exceptions to its own outcome (an exit code, a failed task, a skipped item) through one mapping per edge, and it is the only place where logging a failure and moving on is acceptable. Try/except scattered through business functions complicates control flow, obscures the real logic and tends to return plausible defaults that hide the failure. Fail fast instead: a crash with a clear traceback is more useful than a silently broken program.

## Bad Example

```python
def order_total(order_id: str) -> Decimal:
    try:
        order = ORDERS[order_id]
    except KeyError:
        return Decimal(0)  # "not found" and a typo both read as an empty order
    try:
        return sum((line.price * line.quantity for line in order.lines), Decimal(0))
    except Exception:
        logger.error("total failed")
        return Decimal(-1)  # a sentinel the caller can forget to check
```

## Good Example

```python
class SqlOrderRepository:
    def get(self, order_id: str) -> Order:  # the adapter translates the lookup
        row = self._fetch_row(order_id)
        if row is None:
            raise OrderNotFoundError(order_id)
        return to_order(row)


def order_total(order: Order) -> Decimal:  # business code just computes
    return sum((line.price * line.quantity for line in order.lines), Decimal(0))


def main(argv: list[str]) -> int:
    try:
        run(parse_args(argv))
    except AppError as exc:  # the one place domain errors become an exit code
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0
```

## Notes

- Business code never raises framework exceptions. For the web edge, the status mapping and the exception handlers are in fastapi-error-boundaries (web-application skill).
- Never let `KeyError`, `IndexError` or `AttributeError` cross a layer as a signal. Translate at the adapter that did the lookup (`raise OrderNotFoundError(order_id) from exc`); otherwise a typo in business code reads as "not found".
- Never signal failure with sentinels or error dicts (`None`, `-1`, `False`, `{"error": ...}`): a caller can forget to check a sentinel but cannot ignore an exception.
- Return one type from every path. A `Command | bool` that returns `False` on failure is a sentinel: raise instead, or return `Command | None` where absence is a normal outcome.
- Follow the codebase's existing absence convention. If it has none, required lookups raise a domain not-found error, `T | None` is returned only where absence is a normal outcome, and the function name makes the difference visible to the caller.
- Validate where data enters (request parsing, config loading, file readers) and trust the validated values inside: helpers called only by validated code do not re-check.
- Let unexpected exceptions reach the default handler instead of wrapping internal calls defensively. A catch-all at the edge that maps every failure to one outcome hides real problems behind a misleading message.
- Log and continue only at a boundary with a defined non-success outcome. An intentional fallback is documented where it happens, observable (a warning log that names the cause) and limited to named exceptions; never return a plausible-looking default for a failure nobody expected.
- error-flow.md follows one failure along its path: where it is raised, translated, logged or retried.
