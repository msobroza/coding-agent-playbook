---
id: python-idioms
name: Idioms
description: "Match the file's conventions, keep os.path for legacy str APIs, read whole files with read_text, use f-strings, and never shadow builtins."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: idioms
priority: 72
tags: [python, style]
---

# Follow the small house idioms

## Description

Small conventions that keep Python files uniform, so a reader never stops to ask why two files do the same thing differently. Follow them in new code. When you edit an existing file that does something differently, match the file so it stays consistent, and leave a wider cleanup to its own change.

The always-loaded house style owns paths and the explicit text encoding; this rule adds only the exception and the calls to use. `os.path` is acceptable only where a legacy standard-library call needs a `str`. Read or write a whole text file with `Path.read_text` and `Path.write_text`, not `open(...).read()`, which leaves the file handle open until the garbage collector closes it.

## Bad Example

```python
def count_lines(path):  # no type hints, no encoding, no Path, a leaked file handle
    return len(open(path).read().splitlines())


def describe(id, total):  # `id` shadows the builtin for the whole function
    return "Order %s: %d lines" % (id, total)  # %-formatting
```

## Good Example

```python
def count_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def describe(order_id: str, total: int) -> str:
    return f"Order {order_id}: {total} lines"
```

## Notes

- Use f-strings (`f"hello, {name}"`), not `%`-formatting or `.format()`. A template filled in later, such as a logging call's lazy arguments or a translated message, is the exception.
- Use double quotes, and single quotes only when the string contains a double quote. Where Ruff or Black is configured, let the formatter decide.
- Don't shadow builtins (`list`, `dict`, `id`, `type`, `input`, `map`, `filter`, `vars`) with local names or parameters: the builtin becomes unreachable in that scope, and a later call to it fails far from the cause. Name the role instead (`items`, `order_id`, `account_type`).
