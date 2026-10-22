---
id: ruff-lint
name: Linting with ruff
description: "Fix what the repo's ruff selection reports at its cause; never trim the selection, and suppress only with a code and a reason."
version: 1
scope: scoped
globs:
  - "**/*.py"
  - "pyproject.toml"
  - "ruff.toml"
  - ".ruff.toml"
section: linting
priority: 21
tags: [python, tooling, ruff]
---

# Linting with ruff

## Description

Ruff replaces flake8, isort, pyupgrade and many other tools with a single linter. The rule selection in `[tool.ruff.lint]` (in `pyproject.toml` or `ruff.toml`) is the repo's decision: fix what it reports, never trim it.

## Bad Example

```toml
[tool.ruff.lint]
select = ["E", "F", "B", "SIM"]
ignore = ["B006"]  # added to get CI green
```

```python
def add_tag(tag: str, tags: list[str] = []) -> list[str]:  # noqa
    tags.append(tag)
    return tags
```

## Good Example

An illustration of the shape a selection takes, not settings to adopt:

```toml
[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "F",    # Pyflakes
    "W",    # pycodestyle warnings
    "I",    # isort
    "UP",   # pyupgrade
    "B",    # flake8-bugbear
    "BLE",  # flake8-blind-except
    "SIM",  # flake8-simplify
    "PTH",  # flake8-use-pathlib
    "RUF",  # Ruff-specific rules
]
unfixable = [
    "F841",    # unused variable: read it, then delete it yourself
    "ERA001",  # commented-out code: read it, then delete it yourself
]

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = [
    "S101",     # assert is fine in tests
    "ARG001",   # unused fixtures
    "PLR2004",  # magic values are fine in tests
]
"__init__.py" = ["F401"]  # re-exports
```

Fix a finding at its cause; when a suppression is the right call, name the code and the reason:

```python
import invoicing.plugins  # noqa: F401  # registers the plugins on import


def add_tag(tag: str, tags: list[str] | None = None) -> list[str]:
    return [*(tags or []), tag]
```

```bash
ruff check .                # the check, as CI runs it
ruff check . --fix          # apply the safe fixes
ruff check . --statistics   # count findings per code
```

## Notes

- Read every unsafe fix before applying it (`--unsafe-fixes`): ruff holds them back because they can change behavior.
- A scoped `per-file-ignores` entry beats a global `ignore`, and both are proposed to the user, not edited. A whole-file or whole-directory entry needs the user's agreement.
- `target-version`, or `requires-python` when it is unset, decides which UP fixes appear; never change it to silence one.
- The broad-handler codes BLE001, S110 and S112 belong to python-error-handling. A handler BLE001 lets through because it logs the exception must still be a real boundary, not a swallowed failure.
- Propose new codes to the user as an `extend-select` change sized with `ruff check --statistics`; never preview-only codes unless the repo already runs preview.
- Delete dead code your change creates or touches (F401, F841, ERA001) instead of suppressing it: version control keeps the history. Dead code in untouched files is reported (`project-context`).
