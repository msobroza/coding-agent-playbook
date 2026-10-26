---
id: python-uv-workflow
name: uv workflow
description: "In a uv project, change dependencies only through uv, run everything through the project environment, and leave uv.lock to uv."
scope: scoped
globs:
  - "pyproject.toml"
applies_if:
  package_manager: uv
section: package-management
priority: 60
tags: [python, tooling, uv]
---

# uv workflow

## Description

This repo is a uv project: `pyproject.toml` declares what the project needs, `uv.lock` records the exact versions that satisfy it, and uv keeps the environment in step with both. Every change goes through uv's project workflow (`uv add`, `uv lock`, `uv sync`, `uv run`), so the declaration, the lock and the environment never drift apart.

## Bad Example

```bash
pip install httpx         # lands outside the lock; the next uv sync removes it
uv pip install httpx      # the same, through uv's pip interface
uv lock --upgrade         # upgrades every package, unasked
```

A hand edit of `uv.lock` to bump one version goes wrong the same way: the lock no longer matches what uv resolves.

## Good Example

```bash
# Add or remove a dependency: only when the task needs it and the user agreed.
uv add httpx                   # runtime; rewrites pyproject.toml and uv.lock
uv add --dev pytest            # the dev dependency group
uv add --group docs mkdocs     # another dependency group
uv remove httpx

# Run project commands inside the project environment (it syncs first).
uv run pytest -q
uv run python -m invoicing

# Upgrade one package the task needs.
uv lock --upgrade-package httpx
```

| Environment | Command |
| --- | --- |
| Development | `uv sync` |
| CI | `uv sync --locked` (fails when `uv.lock` is out of date) |
| Production | `uv sync --locked --no-dev` |

## Notes

- Never edit `uv.lock` by hand, and never run `pip install` or `uv pip install` against the project environment. With hooks on, the dependency guard denies both.
- Run `uv sync` after pulling changes that touch `pyproject.toml` or `uv.lock`, and commit the two files together: a CI job that installs with `uv sync --locked` fails when the lock no longer matches the declaration.
- Commit `uv.lock`; never commit `.venv/`. Use `uv sync --frozen` only when you intentionally skip the freshness check and trust the existing lock.
- Run a one-off tool with `uvx <tool>` (for example `uvx ruff check .`) instead of adding it to the project.
- Upgrade the whole lock only when the user asks for it, as its own change.
- If the `uv` command is not available, stop and ask the user how they want to proceed. Never install uv yourself, and never download and run an installer script.
- Where each dependency is declared, and with which bounds, is python-pyproject-dependencies'.
- uv-dependency-failures.md routes a failed lock check, a missing import or a dependency-guard denial to its uv command and rule.
