---
id: pytest-configuration
name: pytest configuration
description: "Keep pytest settings in the one place the repo already uses, register every marker, filter warnings narrowly, and never lower the coverage bar."
version: 1
scope: scoped
globs:
  - "pyproject.toml"
  - "pytest.ini"
  - "tox.ini"
  - "setup.cfg"
  - "**/conftest.py"
applies_if:
  has_framework: ["pytest"]
section: test-configuration
priority: 42
tags: [python, tooling, pytest]
---

# pytest configuration

The suite's settings are shared by everyone who runs it, locally and in CI. Change them rarely, in one place, and only in ways that keep a failing run failing.

## One home for the settings

- pytest reads its settings from one file: `[tool.pytest.ini_options]` in `pyproject.toml`, `pytest.ini`, `tox.ini` or `setup.cfg`. Edit the one this repo already uses; never start a second.
- Leave `addopts` alone for personal preferences. Flags such as `-x`, `-v` or coverage options change every run for everyone; pass them on your own command line instead.

## Markers

- Register every custom marker under `markers`, with a one-line meaning. With strict markers on, a typo in `@pytest.mark.slwo` then fails collection instead of silently selecting nothing.
- Select subsets with `-m` (`pytest -m "not slow"`). When to skip or expect a failure is the `pytest` rule's call.

## Warnings

- When the repo turns warnings into errors, a warning from our own code is a bug: fix its cause.
- Filter a third-party warning narrowly, by message, category and module, with a comment saying why and when it can go. Never ignore a whole category.

```toml
[tool.pytest.ini_options]
filterwarnings = [
    "error",
    # The carrier SDK still calls a deprecated datetime API; drop once it is upgraded.
    "ignore:datetime.datetime.utcnow:DeprecationWarning:carrier_rates_sdk",
]
```

The values are an example of the shape, not settings to adopt.

## Coverage

- Keep the configured threshold and the branch setting as they are; never lower either to get a change through.
- Mark a line `# pragma: no cover` only when no test can reach it (a platform guard, an `if TYPE_CHECKING:` block), with a comment giving the reason.

## Discovery

- Put new tests where `testpaths` and the configured file patterns find them. Check with `pytest --collect-only -q` that a new test is collected before relying on it passing.
- Rerun only the last failures with `pytest --lf` while fixing, then run the whole suite before you report the work done.
