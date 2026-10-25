---
id: python-pyproject-dependencies
name: Declaring dependencies
description: "Declare runtime dependencies with lower bounds, development tools in dependency groups and optional features as extras; never pin exactly in a library or touch requires-python unasked."
scope: scoped
globs:
  - "pyproject.toml"
applies_if:
  package_manager: uv
section: package-management
priority: 61
tags: [python, tooling, uv]
---

# Declaring dependencies in pyproject.toml

## Description

`pyproject.toml` is the single configuration file for modern Python projects. It holds the project metadata, the dependencies and each tool's settings in one place, following PEP 621. Each kind of dependency has its own table:

| Section | Purpose |
| --- | --- |
| `[project]` | Package metadata and runtime `dependencies` (PEP 621) |
| `[dependency-groups]` | Development, test and lint tools; never installed by users |
| `[project.optional-dependencies]` | Optional runtime features users install |
| `[project.scripts]` | Command-line entry points |
| `[build-system]` | The build backend; keep the repo's table as it is |
| `[tool.<name>]` | One tool's settings |

## Bad Example

```toml
[project]
requires-python = ">=3.12"  # raised to use a newer feature, unasked
dependencies = [
    "httpx==0.27.2",  # an exact pin in a library forces this version on every installer
]

[project.optional-dependencies]
dev = ["ruff>=0.8", "mypy>=1.13"]  # tools published as an extra users can install
test = ["pytest>=8"]
```

## Good Example

The versions only show the shape; follow the bounds the repo already uses.

```toml
[project]
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.6",
]

[project.optional-dependencies]
pdf = ["weasyprint>=60"]  # an optional feature users install

[project.scripts]
invoicing = "invoicing.cli:main"

[dependency-groups]
dev = ["ruff>=0.8", "mypy>=1.13"]
test = ["pytest>=8", "pytest-cov>=4"]
```

## Notes

- Runtime dependencies take a lower bound (`>=`), not an exact pin: the lock pins versions, and an exact pin in a library's metadata forces that one version on every project that installs it.
- Tools used only to develop, test or lint go in a dependency group, never in `[project].dependencies` or an extra.
- Use extras only for optional runtime features users install.
- Leave `requires-python` and `.python-version` unchanged unless the user asks; they decide which interpreters the project supports.
- Each tool's settings live in its own `[tool.<name>]` table.
- Keep the existing `[build-system]` table as it is; a backend change is the user's decision.
- Adding or removing a dependency goes through python-uv-workflow (`uv add`, `uv remove`), after the user agreed.
