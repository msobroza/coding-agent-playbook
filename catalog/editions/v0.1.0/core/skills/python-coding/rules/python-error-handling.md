---
id: python-error-handling
name: Error handling
description: "Catch only the narrowest exception you can handle, never swallow one, and chain with raise ... from when you translate it."
scope: scoped
globs:
  - "**/*.py"
section: errors
priority: 20
tags: [python, errors]
lint_codes:
  warn: [E722, BLE001, S110, S112, B904, TRY400, TRY401, S101]
---

# Never swallow exceptions

## Description

Catch an exception only when the current layer can recover, add meaningful context, or handle it at an application boundary. Otherwise let it propagate: that is the default. Never hide an unexpected failure with `pass`, `continue`, an unexplained default value, or a log message followed by code that treats the operation as successful. Silent failures make corrupted or incomplete results look successful and remove the traceback needed to diagnose the cause.

## Bad Example

```python
def load_settings(path: Path) -> Settings:
    try:
        return Settings.from_json(path.read_text(encoding="utf-8"))
    except Exception:
        pass

    return Settings()  # invalid JSON, I/O failures and typos all look like valid defaults


def parse_amount(user_input: str) -> int | str:
    try:
        return int(user_input)
    except:  # also catches KeyboardInterrupt and the NameError of a typo
        return "error"
```

## Good Example

```python
class SettingsError(AppError):
    """Raised when application settings cannot be loaded."""


def load_optional_settings(path: Path) -> Settings:
    """Load settings; a missing optional file means use defaults."""
    try:
        content = path.read_text(encoding="utf-8")
        return Settings.from_json(content)
    except FileNotFoundError:
        return Settings()  # expected absence, not degraded behavior
    except (OSError, ValueError) as exc:
        raise SettingsError(f"failed to load settings from {path}") from exc


def parse_amount(user_input: str) -> int:
    try:
        return int(user_input)
    except ValueError as exc:
        raise InvalidAmountError(f"expected a whole number, got {user_input!r}") from exc
```

## Notes

- Catch the narrowest types you can handle: `except ValueError` beats `except Exception`, and a bare `except:` is never acceptable. Use one `except` clause per failure mode when each needs a different response.
- `except Exception` is acceptable only when the recovery ends by surfacing the error: roll back or clean up, then re-raise. A retry catches only an explicit set of transient errors, never `Exception`.
- A broad catch hides real bugs. `NameError`, `AttributeError` and `TypeError` from a typo or a wrong call are programming errors that should crash with a clear traceback, not turn into a plausible result.
- If a function cannot recover or add useful context, do not catch the exception. Logging and then `pass` is still swallowing.
- Logging is not recovery. Log and suppress only at an explicit boundary, such as a task supervisor or a command entry point, where the failure stays observable and becomes a defined non-success outcome (a failed task state, a nonzero exit code); `python-error-boundaries` says where those are.
- Never suppress cancellation or process-control exceptions: `asyncio.CancelledError`, `KeyboardInterrupt` and `SystemExit` propagate, unless the boundary cleans up and re-raises them.
- Intentional degraded behavior is a fallback, and `python-error-boundaries` says how to document it. The documented absence of an explicitly optional resource is a normal condition, not degraded behavior.
- When you translate an exception, `raise NewError(...) from exc` keeps the original traceback visible; `from None` deliberately hides it, for an inner exception that is noise the caller cannot act on.
- `assert` is stripped when Python runs with `-O`. It documents invariants in tests and tight internal loops; it never validates user input and never guards security. Use `if ... raise` for anything that must hold at runtime:

```python
def withdraw(account: Account, amount: int) -> None:
    if amount < 0:
        raise ValueError(f"amount must be non-negative, got {amount!r}")  # good
    assert amount >= 0, "amount must be non-negative"  # never; -O removes it
```

- Log an exception with `logger.exception("what failed")` inside the `except` block, which records the traceback; never `logger.error(str(exc))`, which loses the stack. Keep secrets, tokens and personal data out of the message.
- Ruff's E722, BLE001, S110, S112, B904, TRY400, TRY401 and S101 flag these patterns where the repo's ruff settings enable them. They supplement review: a handler that only logs passes the lint and can still swallow a failure.
