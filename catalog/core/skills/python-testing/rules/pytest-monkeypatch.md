---
id: pytest-monkeypatch
name: pytest monkeypatch
description: "Change environment variables, the working directory, dict entries and legacy module attributes only through the monkeypatch fixture, which undoes every change; in new code, a needed patch means a parameter is missing."
version: 1
scope: scoped
globs:
  - "tests/**/*.py"
  - "**/conftest.py"
applies_if:
  has_framework: ["pytest"]
section: isolation
priority: 47
tags: [python, testing, pytest, isolation, monkeypatch]
---

# Use monkeypatch for environment variables and attributes

## Description

pytest's `monkeypatch` fixture changes environment variables (`setenv`, `delenv`), dict entries (`setitem`), the working directory (`chdir`) and attributes (`setattr`), and undoes every change when the test ends, even when it fails. Assigning to `os.environ` or to a module global directly, or a hand-written set-then-restore, leaks the change into every later test once an assertion fails before the restore, and the suite starts failing by run order.

## Bad Example

```python
import os
from pathlib import Path


def test_reads_api_key() -> None:
    os.environ["API_KEY"] = "test-key"  # leaks into every following test

    config = load_config()

    assert config.api_key == "test-key"
    del os.environ["API_KEY"]  # skipped when the assert fails


def test_export_writes_to_the_export_dir() -> None:
    reports.EXPORT_DIR = Path("/srv/exports")  # permanent for the rest of the session
    assert export_report().parent == Path("/srv/exports")
```

## Good Example

```python
from pathlib import Path

import pytest


def test_reads_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "test-key")  # undone automatically

    config = load_config()

    assert config.api_key == "test-key"


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API_KEY", raising=False)

    with pytest.raises(ConfigError, match="API_KEY"):
        load_config()


def test_export_writes_to_the_export_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Legacy code reads a module constant; restored after the test.
    monkeypatch.setattr(reports, "EXPORT_DIR", tmp_path)

    assert export_report().parent == tmp_path
```

## Notes

- `setattr` is the fallback for code that cannot take a parameter yet, not a lighter mock. In new code, needing a patch means a dependency is hidden: add the parameter (`export_report(export_dir=tmp_path)`) and pass a value or a named fake (`pytest-test-doubles`).
- Read environment variables once at the edge (settings built by the entry point); business code takes plain values and never reads `os.environ`.
- Use `monkeypatch.chdir(tmp_path)` instead of `os.chdir` for the same cleanup guarantee.
- When many tests need the same environment variables, wrap the monkeypatch calls in a fixture instead of repeating them.
- The fixture is function-scoped. For a session-scoped patch, create `patcher = pytest.MonkeyPatch()` inside a session-scoped fixture, `yield`, then call `patcher.undo()`.
- monkeypatch against a fake, autospec or a new parameter: choosing-a-test-double.md.
