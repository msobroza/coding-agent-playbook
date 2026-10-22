---
id: mypy-type-checking
name: Type checking with mypy
description: "Work inside the repo's mypy or pyright settings: fix types before silencing them, scope every override to one module, and hold new code to the strictest level in use."
version: 1
scope: scoped
globs:
  - "**/*.py"
  - "**/*.pyi"
  - "pyproject.toml"
  - "mypy.ini"
  - ".mypy.ini"
  - "pyrightconfig.json"
section: type-checking
priority: 40
tags: [python, tooling, mypy]
---

# Type checking with mypy

## Description

Mypy is a static type checker for Python. It catches type errors before the code runs. The repo runs mypy or pyright, in the workflow and in CI: run it the way CI does, never with stricter or looser flags, and work inside the settings it already has.

## Bad Example

```toml
[tool.mypy]
ignore_missing_imports = true  # silences every untyped import, in every module

[[tool.mypy.overrides]]
module = ["invoicing.legacy_export.*", "invoicing.refunds"]  # new module joins the legacy list
disallow_untyped_defs = false
```

## Good Example

Overrides stay scoped: one legacy package relaxed, one untyped import silenced. The values show the shape; they are not settings to copy.

```toml
# Typed later: new invoicing modules stay out of this list.
[[tool.mypy.overrides]]
module = ["invoicing.legacy_export.*"]
disallow_untyped_defs = false

# The carrier SDK ships no types; silence only that import.
[[tool.mypy.overrides]]
module = ["carrier_rates_sdk.*"]
ignore_missing_imports = true
```

A local stub file types a library you call often, found through `mypy_path`:

```python
# stubs/legacy_ledger/__init__.pyi
from typing import TypedDict


class Entry(TypedDict):
    account: str
    amount_cents: int


class Client:
    def __init__(self, base_path: str) -> None: ...
    def fetch(self, entry_id: str) -> Entry: ...
```

```toml
[tool.mypy]
mypy_path = "stubs"
```

Use `cast()` only where you know more than the checker, with a comment saying what you know:

```python
from typing import cast

# The ledger API returns invoices for an invoice query; its stub says list[object].
invoices = cast("list[Invoice]", ledger.query("invoices"))
```

## Notes

- Fix the types before silencing anything: narrow with `isinstance` or an early return, return a precise type or annotate the variable.
- A new module meets the strictest level the repo applies anywhere. An override that relaxes checks for legacy code stays scoped to that code; never add a new module to it.
- For a third-party import that ships no types, propose a stub package for the dev dependencies to the user, or add a per-module override for that import alone; never repo-wide. Never let mypy install packages itself: stubs reach the environment like any other dependency.
- Run the command CI runs (python-static-checks), not a stricter or looser one of your own.
- Strictness and plugins are the repo's settings. Propose `strict = true`, or a plugin such as `pydantic.mypy` (which lets `Settings()` built from the environment type-check), to the user as a separate change.
- `warn_unused_ignores` reports stale ignores; delete them. `reveal_type()` is for debugging only: remove it before the change is committed.
- Common error codes: `import-untyped`, `no-any-return`, `arg-type`, `assignment`, `attr-defined`. Every ignore names its code (python-typing).
- The same rules hold for pyright's configuration and its `# pyright: ignore[rule]` comments.
