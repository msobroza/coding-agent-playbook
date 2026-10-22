---
id: pytest-configuration
name: pytest configuration
description: "Keep pytest and coverage settings in the one place the repo already uses, register every marker, filter warnings narrowly, and never lower the coverage bar."
version: 1
scope: scoped
globs:
  - "pyproject.toml"
  - "pytest.ini"
  - "tox.ini"
  - "setup.cfg"
  - ".coveragerc"
  - "**/conftest.py"
applies_if:
  has_framework: ["pytest"]
section: test-configuration
priority: 42
tags: [python, tooling, pytest]
---

# pytest configuration

## Description

The suite's settings are shared by everyone who runs it, locally and in CI. Change them rarely, in one place, and only in ways that keep a failing run failing. pytest reads its settings from one file (`[tool.pytest.ini_options]` in `pyproject.toml`, `pytest.ini`, `tox.ini` or `setup.cfg`), and coverage from its own tables or `.coveragerc`: edit the one this repo already uses; never start a second.

## Bad Example

```toml
[tool.pytest.ini_options]
addopts = ["-v", "--tb=short", "-x"]  # personal flags, now on every run for everyone
filterwarnings = [
    "error",
    "ignore::UserWarning",  # a whole category hides the next real warning
]

[tool.coverage.report]
fail_under = 60  # lowered from 80 to get the change through
```

## Good Example

The shape of the settings, not values to adopt:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
addopts = ["--strict-markers", "-ra"]
markers = [
    "slow: marks tests as slow",
    "integration: marks integration tests",
]
filterwarnings = [
    "error",
    # The carrier SDK still calls a deprecated datetime API; drop once it is upgraded.
    "ignore:datetime.datetime.utcnow:DeprecationWarning:carrier_rates_sdk",
]

[tool.coverage.run]
source = ["src"]
branch = true

[tool.coverage.report]
exclude_lines = ["pragma: no cover", "if TYPE_CHECKING:"]
fail_under = 80
```

Flags for one run go on the command line:

```bash
pytest -x                    # stop on the first failure
pytest -k "refund"           # run the matching tests
pytest -m "not slow"         # skip the slow tests
pytest --cov                 # with coverage
pytest --collect-only -q     # is the new test collected?
pytest --lf                  # rerun only the last failures
```

## Notes

- Leave `addopts` alone for personal preferences. Flags such as `-x`, `-v` or coverage options change every run for everyone; pass them on your own command line instead.
- Register every custom marker under `markers`, with a one-line meaning. With strict markers on, a typo in `@pytest.mark.slwo` fails collection instead of silently selecting nothing. Select subsets with `-m`; when to skip or expect a failure is the pytest rule's call (python-testing).
- When the repo turns warnings into errors, a warning from our own code is a bug: fix its cause. Filter a third-party warning narrowly, by message, category and module, with a comment saying why and when it can go.
- Keep the configured threshold and the branch setting as they are; never lower either to get a change through. The configured threshold is the bar. How to read branch coverage is pytest-branch-coverage's (python-testing).
- Mark a line `# pragma: no cover` only when no test can reach it (a platform guard, an `if TYPE_CHECKING:` block), with a comment giving the reason.
- Put new tests where `testpaths` and the configured file patterns find them, and check with `pytest --collect-only -q` that a new test is collected before relying on it passing.
- Rerun only the last failures with `pytest --lf` while fixing, then run the whole suite before you report the work done.
