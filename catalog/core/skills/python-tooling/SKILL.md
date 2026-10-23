---
id: python-tooling
name: python-tooling
description: "Conventions for the developer tools the repo already runs."
playbook:
  use_when: "fixing lint or type-check findings, editing tool settings, or changing dependencies"
  files: "Tool configuration and pyproject.toml"
  sections:
    - id: linting
      title: "Linting"
      impact: CRITICAL
      summary: "Run the repo's checks the way CI runs them and fix findings instead of loosening the settings."
      open_when: "A `ruff check` code other than I001, a commit blocked by pre-commit, a check failing only in CI, or a `# noqa` or lint config edit."
    - id: type-checking
      title: "Type checking"
      impact: HIGH
      summary: "Work inside the repo's mypy or pyright settings; new code meets the strictest level already in use."
      open_when: "mypy or pyright reports an error, or a change edits `[tool.mypy]`, pyright's config, a `.pyi` stub or a `# type: ignore`."
    - id: formatting
      title: "Formatting"
      impact: HIGH
      summary: "The configured formatter owns layout and import order."
      open_when: "`ruff format --check` would reformat a file, imports are unsorted (I001), or code is aligned or wrapped by hand."
    - id: test-configuration
      title: "Test configuration"
      impact: HIGH
      summary: "pytest and coverage settings live in one place and only ever keep a failing run failing."
      open_when: "pytest fails on a marker, a warning filter or the coverage bar, or a change edits pytest or coverage settings."
    - id: package-management
      title: "Package management"
      impact: MEDIUM
      summary: "In a uv project, dependencies, the lock and the environment change only through uv."
      open_when: "A change adds, removes or upgrades a dependency, touches `uv.lock` or `[dependency-groups]`, or the lock check fails."
  references:
    - path: references/check-failures.md
      open_when: "A check fails and its message names a ruff code, a mypy or pyright error code, a format diff or a pytest setting."
    - path: references/uv-dependency-failures.md
      open_when: "A uv command, CI's lock check or the dependency guard fails, or an import is missing from the project environment."
      applies_if:
        package_manager: uv
---

# Python tooling

Conventions for the developer tools a Python repo already runs: the linter, the type checker, the formatter, the test runner's settings and, in a uv project, the package manager. The repo's own configuration and CI commands decide which tools run and how strictly; the rules here say how to work inside them.

## Why these tools matter

| Tool | What it catches |
| --- | --- |
| ruff | Bugs and style violations, before review; it also formats code and sorts imports |
| mypy or pyright | Type errors, before the code runs |
| The test runner | Regressions, so changes can be made with confidence |
| uv, in a uv project | Drift between the declared dependencies, the lock and the environment |

Running these checks in CI and in pre-commit hooks reduces the review burden and keeps quality consistent.

## Quick reference

The commands as CI runs them; copy the exact arguments from the repo's CI workflow, Makefile or pre-commit config. In a uv project, each runs through `uv run`.

```bash
ruff check .                     # lint
ruff check . --fix               # apply the safe fixes
ruff format --check .            # is everything formatted?
ruff format <the files you changed>
mypy                             # type check with the repo's settings
```

The test suite runs with the command CI uses, with coverage where the repo measures it.

## See also

The python-coding skill holds typing, error handling and Pydantic; the python-testing skill holds test code and coverage practice; the web-application skill holds FastAPI wiring and error boundaries.
