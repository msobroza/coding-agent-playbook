---
id: playbook-rule-gates
name: Rule gates
description: "Gate a rule with applies_if on true detector facts, list keys as YAML lists, and keep globs for nudges."
version: 1
scope: scoped
globs:
  - "catalog/**/rules/**/*.md"
  - "catalog/**/rules/**/*.md.j2"
  - "playbook/**/rules/**/*.md"
  - "playbook/**/rules/**/*.md.j2"
  - "src/*/resources/**/rules/**/*.md"
  - "src/*/resources/**/rules/**/*.md.j2"
applies_if:
  playbook_layer: true
section: rules
priority: 25
tags: [playbook, rules]
---

# Gate rules on detector facts that are true

## Description

`applies_if` decides whether a rule renders in a repo. Its keys are ANDed. A list key takes a YAML list, never a bare string: `has_*` needs every name, `any_*` at least one. A skill has no gate of its own: sync writes it while one of its members passes.

| Key | Value |
| --- | --- |
| `python_version` | A comparison (`>=`, `<=`, `==`, `~=`, `>`, `<`), only when the topic does not exist below that version (`match`: `>=3.10`) |
| `has_framework`, `any_framework` | Detector frameworks only: fastapi, flask, django, starlette, pydantic, sqlalchemy, alembic, httpx, requests, aiohttp, click, typer, pytest, pytest-asyncio, pytest-mock, unittest |
| `has_ml_stack`, `any_ml_stack` | numpy, pandas, polars, torch, tensorflow, jax, transformers, scikit-learn, xgboost, lightgbm, matplotlib, seaborn, duckdb |
| `has_dependency`, `any_dependency` | Any runtime or dev dependency by its normalized name: the key for a library on neither list |
| `has_dev_dependency` | A dev dependency only |
| `has_file`, `any_file` | Repo-relative paths, files or directories |
| `package_manager` | `uv`, `poetry`, `pip-tools` or `pip`, or a list meaning any |
| Boolean facts | `has_notebooks`, `has_dockerfile`, `has_ci`, `domino_project`, `playbook_layer` |

## Bad Example

```yaml
applies_if:
  any_framework: fastapi         # a bare string: a list key needs a list
  has_framework: [streamlit]     # not a detector framework: never matches
  has_notebooks: false           # an absent fact matches neither value
  python_version: ">=3.11"       # hides a topic that exists on 3.10
```

## Good Example

A web database rule:

```yaml
applies_if:
  any_framework: [fastapi, flask, django, starlette]
  any_dependency: [sqlalchemy, alembic]
```

## Notes

- Gate on true, never on false: an absent boolean fact matches neither value, and the detector sets `has_notebooks` only when notebooks exist.
- Globs are no gate. They drive the skill nudge (the first edit of a matching file names the skill, the most specific glob first) and Continue's attachment.
- Test rules use the shared test-file glob set: `**/test_*.py`, `**/*_test.py`, `**/tests/**/*.py`, `**/conftest.py`, `**/fakes.py`.
- Prompts, hooks and a skill's reference or example entries take the same predicate language.
- An unknown key fails validate in every repo, whatever its facts.
- `playbook check` prints this repo's facts and, for each skipped rule, the predicate that failed.
- Lists belong in `applies_if`; the helpers that test one name live inside a template (`playbook-rule-templates`).
