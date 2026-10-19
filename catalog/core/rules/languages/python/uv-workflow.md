---
id: python-uv-workflow
name: uv workflow
description: "In a uv project, change dependencies only through uv, run everything through the project environment, and leave uv.lock to uv."
version: 1
scope: scoped
skill: python-tooling
globs:
  - "pyproject.toml"
applies_if:
  package_manager: uv
priority: 28
tags: [python, tooling, uv]
---

# uv workflow

This repo is a uv project: `pyproject.toml` declares what the project needs, `uv.lock` records the exact versions that satisfy it, and uv keeps the environment in step with both. Every change goes through uv, so the declaration, the lock and the environment never drift apart.

## uv owns the environment

- Add a dependency only when the task needs it and the user agreed to it. Then make the change with `uv add <name>`, `uv add --dev <name>` (or `--group <group>` for another dependency group) and `uv remove <name>`, which rewrite the declaration and the lock in one step.
- Never edit `uv.lock` by hand, and never run `pip install` or `uv pip install` against the project environment: the package lands outside the lock, and the next `uv sync` removes it again. With hooks on, the dependency guard denies both.

## Run through the project

- Run project commands with `uv run`, such as `uv run python -m invoicing` for the app and `uv run pytest -q` for the tests. uv syncs the environment before the command starts, so it always matches the lock.
- Run `uv sync` after pulling changes that touch `pyproject.toml` or `uv.lock`. A CI job that installs with `uv sync --locked` fails when the lock no longer matches the declaration, so commit the two files together.
- Run a one-off tool with `uvx <tool>` instead of adding it to the project.

## Lockfile discipline

- `uv.lock` is committed, and only uv writes it.
- Upgrade one package with `uv lock --upgrade-package <name>` when the task needs that upgrade. Upgrading the whole lock is a separate change, made only when the user asks for it.

## Declaring dependencies

- Runtime dependencies go in `[project].dependencies` with a lower bound (`"httpx>=0.27"`). Tools used only to develop, test or lint go in a dev dependency group.
- A library's `pyproject.toml` carries no exact pins: the lock pins versions, and an exact pin in a library's metadata forces that one version on every project that installs it.
- Leave `requires-python` and `.python-version` unchanged unless the user asks; they decide which interpreters the project supports.

```toml
[project]
dependencies = ["httpx>=0.27", "pydantic>=2.6"]

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.6"]
```

The versions above only show the shape; follow the bounds the repo already uses.

## When uv is missing

- If the `uv` command is not available, stop and ask the user how they want to proceed. Never install uv yourself, and never download and run an installer script.
