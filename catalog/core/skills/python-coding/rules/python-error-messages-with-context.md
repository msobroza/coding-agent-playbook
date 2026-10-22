---
id: python-error-messages-with-context
name: Error messages with context
description: "Raise errors whose message names the offending value with repr, the shape that was expected and the input or field it came from."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: errors
priority: 21
tags: [python, errors]
---

# Error messages that carry the offending value

## Description

An error message is the first thing anyone debugging a failure reads. `ValueError("invalid input")` says only that something went wrong, so the reader has to reproduce the failure or add logging to learn what. A message that names the value it received (formatted with `repr`), the shape it expected and, where useful, the input or field it came from explains the failure at once. Every reader gains from this: a person reading a traceback, an on-call engineer reading a log line, and a coding agent, for which a vague message costs an extra round of investigation before it can fix anything.

## Bad Example

```python
def parse_port(raw: str) -> int:
    port = int(raw)
    if not 0 < port < 65536:
        raise ValueError("invalid input")
    return port


def load_retry_count(config: Mapping[str, str]) -> int:
    try:
        return int(config["retries"])
    except ValueError:
        raise ConfigError("bad config")  # no value, no field, and the cause is lost
```

## Good Example

```python
def parse_port(raw: str, *, field: str = "port") -> int:
    port = int(raw)
    if not 0 < port < 65536:
        raise ValueError(f"{field}: expected an integer from 1 to 65535, got {raw!r}")
    return port


def load_retry_count(config: Mapping[str, str]) -> int:
    raw = config["retries"]
    try:
        return int(raw)
    except ValueError as err:
        raise ConfigError(f"retries: expected a whole number, got {raw!r}") from err
```

## Notes

- Format the value with `!r`, so empty strings, stray whitespace, `None` and type differences show: `got ''` and `got '8080 '` read differently from `got 8080`.
- State the expectation concretely: a range, a format, the allowed choices or the expected type.
- Keep the cause with `raise ... from err` when you translate an exception: the message adds the context, the chain keeps the original traceback.
- For a large value, show a bounded excerpt or its length, never a whole payload.
- Never put secrets, tokens or personal data in a message; name the field and describe what is wrong with it instead. `python-error-handling` owns what may be logged.
- A custom exception class also carries the values as attributes, so a handler can read them without parsing the message; `python-custom-exceptions` shows the pattern.
