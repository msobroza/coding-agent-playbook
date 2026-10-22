---
id: python-static-checks
name: Static checks
description: "Treat the repo's ruff and mypy settings as the contract: run what CI runs, fix every finding your change introduces, and never loosen a check to make one disappear."
version: 1
scope: scoped
globs:
  - "**/*.py"
  - "pyproject.toml"
  - "ruff.toml"
  - ".ruff.toml"
  - "mypy.ini"
  - ".mypy.ini"
section: linting
priority: 20
tags: [python, tooling, ruff, mypy]
---

# Static checks

The linter and the type checker are the cheapest reviewers a repo has. Their settings record decisions the team already made, so work inside them: read them, run the checks the way CI runs them, and leave every check at least as strict as you found it.

## The settings are the contract

- Before acting on a finding, read the repo's settings: `[tool.ruff]` in `pyproject.toml` or a `ruff.toml`, and `[tool.mypy]` or a `mypy.ini`. They decide which codes are on, which paths are excluded and how strict the typing is.
- Never edit `select`, `ignore`, `per-file-ignores` or the mypy strictness to make a finding go away. When a setting looks wrong, propose the change to the user as a separate step, naming the finding that prompted it.

## Run what CI runs

- Use the repo's own lint and type-check commands. They live in the CI workflow, the Makefile or the pre-commit config; run them with the same arguments, because a bare `ruff check` on one file can miss paths or options CI applies.
- Fix every finding your change introduces before you call the work done. A finding in code you did not touch is a problem outside the task: report it (`project-context`) rather than fixing it in the same change.

## Ruff

- Apply safe fixes with `ruff check --fix`. Read each unsafe fix before you accept it: ruff holds those back because they can change behavior.
- The formatter owns layout. Never hand-align columns, wrap lines your own way or undo a format run; when a construct formats badly, restructure the code instead.
- Import order follows the configured isort settings. Let the fixer sort imports rather than ordering them by hand.

## Suppressions

- Every suppression names its code and says why (`python-house-style`). Two habits go with that rule.
- Delete a stale `# noqa` or `# type: ignore[...]` on a line you touch: a comment that no longer silences anything hides the next real finding.
- Add a whole-file or whole-directory entry to `per-file-ignores` only with the user's agreement.

## mypy

- Fix the types before silencing anything: narrow with `isinstance`, return a precise type or annotate the variable.
- Use `typing.cast()` only where you know more than the checker does, with a comment saying what you know.
- For a third-party import that ships no types, propose a stub package for the dev dependency group to the user, or add a per-module override for that import alone. Never switch the check off for the whole repo, and never let mypy install packages itself: stubs reach the environment through the dev group, like any other dependency.
- `reveal_type()` is for debugging. Remove it before the change is committed.

## New code meets the strictest level

- A new module meets the strictest level the repo applies anywhere. An override that relaxes checks for legacy code stays scoped to that code; never add a new module to it.

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

- The values above illustrate the shape of an override; they are not settings to copy. The repo's own configuration decides which checks are on and how strict they are.
