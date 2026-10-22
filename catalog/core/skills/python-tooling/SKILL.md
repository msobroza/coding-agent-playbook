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
---

# Python tooling

Conventions for the developer tools a Python repo already runs: the linter, the type checker, the formatter, the test runner's settings and, in a uv project, the package manager. The repo's own configuration and CI commands decide which tools run and how strictly; the rules here say how to work inside them.

## Why these tools matter

| Tool | What it catches |
| --- | --- |
| ruff | Bugs and style violations, early, with fast static analysis; it also formats code and sorts imports |
| mypy or pyright | Errors before runtime, through type checking; it also improves IDE completion |
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

## Picking rules

The rules index in this file lists only the rules that apply to this repo, grouped by section, most important first, each with the one line it requires. Open every rule whose line matches the change and read it in full before writing code or editing configuration.

- A lint finding, a suppression comment, a pre-commit hook or a check that fails only in CI: static checks, linting with ruff.
- A type error, a stub file or type-checker settings: type checking with mypy.
- Layout, line wrapping or import order: formatting with ruff.
- Test-runner settings, markers, warning filters or coverage thresholds: the test runner's configuration.
- Adding, removing or upgrading a dependency, the lockfile, or running project commands: uv workflow, declaring dependencies.

## See also

The python-coding skill holds typing, error handling and Pydantic; the python-testing skill holds test code and coverage practice; the web-application skill holds FastAPI wiring and error boundaries.
