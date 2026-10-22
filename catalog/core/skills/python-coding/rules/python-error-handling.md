---
id: python-error-handling
name: Error handling
description: "Catch only what you can handle, never swallow an exception, chain with raise ... from, and translate errors once at the boundary."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: errors
priority: 20
tags: [python, errors]
lint_codes:
  warn: [E722, BLE001, S110, S112, B904, TRY400, TRY401, S101]
---

# Python error handling

The default for error handling is to let exceptions propagate. Catch only when you can do something meaningful about the failure.

## What to catch

- No bare `except:`. `except Exception` is the loosest acceptable form, and only when the recovery ends by surfacing the error (roll back or clean up, then re-raise). A retry catches only an explicit set of transient errors, never `Exception`. Logging and continuing is allowed only at an isolation boundary (see "Across layers").
- Catch the most specific type you actually expect. `except ValueError` beats `except Exception` beats `except:`.
- No `try`/`except` without a concrete recovery. Don't swallow exceptions to "make it pass": `except Exception: pass` is never acceptable, and logging then `pass` is still swallowing.
- Cancellation and process-control exceptions (`asyncio.CancelledError`, `KeyboardInterrupt`, `SystemExit`) always propagate. A boundary that must clean up when one arrives catches it, cleans up, and re-raises it.

## Chaining

When you wrap a low-level exception in a domain-level one, preserve the cause with `raise ... from`:

```python
try:
    payload = json.loads(text)
except json.JSONDecodeError as exc:
    raise ConfigError(f"invalid config at {path}") from exc
```

`from exc` keeps the original traceback visible; `from None` deliberately hides it (use when the inner exception is noise the caller can't act on).

## Custom exceptions

- Every project gets one base exception class. App-level exceptions inherit from it, never directly from `Exception`. This lets callers do `except MyAppError` and catch the whole family.
- Name the exception after the failure mode, not the location. `ConfigParseError` is better than `ConfigParserError`.

## Across layers

- Raise in the core; translate once, at the boundary. Only entry points (an HTTP handler or exception handler, a CLI `main`, a worker loop, a per-item batch loop) catch domain exceptions, through one mapping per edge. Business code never raises framework exceptions.
- Those entry points are the isolation boundaries: the only places where logging a failure and moving on to the next request, message or item is acceptable.
- Never let `KeyError`, `IndexError` or `AttributeError` cross a layer as a signal. Translate at the adapter that did the lookup (`raise OrderNotFoundError(order_id) from exc`); otherwise a typo in business code reads as "not found".
- Never signal failure with sentinels or error dicts (`None`, `-1`, `False`, `{"error": ...}`). Raise instead: a caller can forget to check a sentinel but cannot ignore an exception.
- Follow the codebase's existing absence convention. If it has none, required lookups raise a domain not-found error, `T | None` is returned only where absence is a normal outcome, and the function name makes the difference visible to the caller.
- `ValueError` and `TypeError` are for violations of the argument contract. Domain failures get subclasses of the project base exception, with the offending identifier in the message.
- Validate where data enters (request parsing, config loading, file readers) and trust the validated values inside. Let unexpected exceptions reach the default handler instead of wrapping internal calls defensively.
- An intentional fallback is documented where it happens, observable (a warning log that names the cause) and limited to named exceptions. Never return a plausible-looking default for a failure nobody expected.

```python
def main(argv: list[str]) -> int:
    try:
        run(parse_args(argv))
    except AppError as exc:  # the one place domain errors become an exit code
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0
```

## `assert` is not a runtime check

`assert` statements are stripped when Python runs with `-O`. They're for invariant documentation in tests and tight internal loops — never for user-input validation, never for security checks. Use an `if ... raise` for anything that has to hold at runtime.

```python
def withdraw(account: Account, amount: int) -> None:
    if amount < 0:
        raise ValueError("amount must be non-negative")  # good
    assert amount >= 0, "amount must be non-negative"  # never; -O removes it
    ...
```

## Logging exceptions

- Use `logger.exception("describe what failed")` inside an `except` block — it includes the traceback automatically.
- Don't `logger.error(str(exc))`; that loses the stack and makes the failure unactionable.
- Don't include secrets, tokens, or PII in the message. The traceback variables are already going somewhere; the message is the human-readable summary.
