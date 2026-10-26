---
id: python-static-checks
name: Static checks
description: "Treat the repo's lint and type-check settings as the contract: run the checks the way CI runs them, fix every finding your change introduces, and never loosen or bypass a check."
scope: scoped
globs:
  - "**/*.py"
  - "pyproject.toml"
  - "ruff.toml"
  - ".ruff.toml"
  - "mypy.ini"
  - ".mypy.ini"
  - "pyrightconfig.json"
  - ".pre-commit-config.yaml"
section: linting
priority: 20
tags: [python, tooling, ruff, mypy]
---

# Run the repo's checks the way CI runs them

## Description

The linter and the type checker are the cheapest reviewers a repo has. Their settings record decisions the team already made, so work inside them: read them, run the checks the way CI runs them, and leave every check at least as strict as you found it.

- The settings are the contract. Never edit `select`, `ignore`, `per-file-ignores` or the type checker's strictness to make a finding go away.
- Run the repo's own lint, format-check and type-check commands. They live in the CI workflow, the Makefile or the pre-commit config; use them with the same arguments, because a bare run on one file can miss the paths or options CI applies.

## Bad Example

```bash
# Default arguments on one file: both pass, while CI's command fails on the package.
ruff check src/orders.py
mypy src/orders.py

# The pre-commit hook failed, so the commit skips it.
git commit --no-verify -m "fix: round order totals"
```

## Good Example

```bash
# The commands copied from the CI workflow, with CI's arguments.
ruff check .
ruff format --check .
mypy

# Where the repo runs its checks as pre-commit hooks, run every hook.
pre-commit run --all-files
```

## Notes

- Read the settings before acting on a finding: `[tool.ruff]` in `pyproject.toml` or a `ruff.toml`, `[tool.mypy]` or a `mypy.ini`, and pyright's configuration. They decide which codes are on, which paths are excluded and how strict the typing is.
- When a setting looks wrong, propose the change to the user as a separate step, naming the finding that prompted it.
- Fix every finding your change introduces before you call the work done. A finding in code you did not touch is outside the task: report it (project-context) rather than fixing it in the same change.
- Every suppression names its code and says why (python-house-style). Delete a stale `# noqa` or `# type: ignore[...]` on a line you touch: a comment that no longer silences anything hides the next real finding.
- A failing pre-commit hook is a finding to fix. Never bypass it with `--no-verify` or `SKIP=`; when a hook rewrites files, read the rewrite, stage it and commit again.
- Adding or changing a hook is a settings change proposed to the user. A hook example uses `repo: local` with `language: system`, so it runs the tools the project already installs:

```yaml
repos:
  - repo: local
    hooks:
      - id: ruff-check
        name: ruff check
        entry: ruff check
        language: system
        types: [python]
```

- The tool rules hold the detail: ruff-lint for lint findings and suppressions, ruff-format for layout and import order, mypy-type-checking for type errors and overrides.
- check-failures.md maps a failing check's code or message to the rule that explains the fix.
