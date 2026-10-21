---
id: python-tooling
name: python-tooling
description: "Conventions tied to a named tool or framework."
playbook:
  use_when: "editing tool configuration or code wired to a framework"
  files: "Tool configuration and framework wiring"
---

# Python tooling

Conventions tied to one named developer tool or framework: the linter and type checker, the test runner's settings, the package manager, input validation models and web framework wiring. Library-agnostic conventions stay in the python-coding skill, and test code in the python-testing skill; a rule here adds only what its tool or framework changes.

## Picking rules

The rules index in this file lists only the rules that apply to this repo, most important first, each with the one line it requires. Open every rule whose line matches the change and read it in full before writing code or editing configuration.

- A lint or type-check finding, a suppression comment, or ruff or mypy settings: static checks.
- Test-runner settings, markers, warning filters or coverage thresholds: the test runner's configuration.
- Adding, removing or upgrading a dependency, the lockfile, or running project commands: uv workflow.
- Parsing untrusted input or loading settings into models: Pydantic boundaries.
- Web apps, routers, dependency providers or error handlers: FastAPI app wiring and FastAPI error boundaries.
