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

Conventions tied to one named developer tool: the linter, the type checker, the formatter, the test runner's settings and the package manager. Line- and function-level Python conventions, Pydantic validation included, stay in the python-coding skill, test code in the python-testing skill, and web framework wiring in the web-application skill; a rule here adds only what its tool changes.

## Picking rules

The rules index in this file lists only the rules that apply to this repo, grouped by section, most important first, each with the one line it requires. Open every rule whose line matches the change and read it in full before writing code or editing configuration.

- A lint or type-check finding, a suppression comment, or ruff or mypy settings: static checks.
- Test-runner settings, markers, warning filters or coverage thresholds: the test runner's configuration.
- Adding, removing or upgrading a dependency, the lockfile, or running project commands: uv workflow.
