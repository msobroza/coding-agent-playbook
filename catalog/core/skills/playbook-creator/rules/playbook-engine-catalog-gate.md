---
id: playbook-engine-catalog-gate
name: Engine catalog gate
description: "In the engine repository, change content and the tests that pin it together, then run the catalog tests and the CI-parity gate."
scope: scoped
globs:
  - "catalog/**"
  - "tests/core_skill_pins/**"
  - "tests/hook_runtime/handlers/**"
  - "tests/plugins/**"
  - "tests/core_skills/**"
applies_if:
  playbook_layer: true
  has_file: [catalog/core]
section: validation
priority: 29
tags: [playbook, validation]
---

# Change engine content and its pins together

## Description

In the engine repository, tests pin the shipped content, so a content change and its pins land in the same commit:

- `tests/core_skill_pins/<skill>.py`: a core skill's members in index order, its probe-inactive members and the frontmatter of kept rules.
- `tests/hook_runtime/handlers/<pack>/`: one test module per hook and its manifest row; every core hook with a body declares a summary.
- `tests/plugins/<name>/`: a bundled plugin's inventory and gates.
- The eval sample proofs: each gate fails on `setup/` and on every negative, and passes on the solution.
- Rule size over a fact matrix: 100 lines and 750 words on every branch.
- Description budgets: core descriptions at most 2,800 characters and core plus each bundled plugin at most 7,000 on the standard probe; 3,400 and 7,500 on the Domino probe.
- The ATTRIBUTIONS mapping test: a new core skill file is either a mapping target or listed in its skill's Engine-written list in `catalog/core/ATTRIBUTIONS.md`; and the self-containment scans for URLs and source names.

Run the config-less `playbook validate` in the checkout, then the catalog tests (the catalog-checks pre-commit hook runs them when `catalog/` is staged), then the CI-parity gate from the repo root, with no path arguments, in the dev environment.

## Bad Example

```bash
pytest tests/integration/test_core_skills.py   # one file, then push
```

The skill's pins, budgets and attribution checks live in other files; a literal rule count edited in a shared test to make it pass hides the change from review.

## Good Example

```bash
uv sync --extra dev
uv run playbook validate
uv run pytest -q -m catalog
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q
```

## Notes

- `ruff format --check .` also formats the Python code blocks inside Markdown, so run `ruff format` on new content first.
- Ruff never touches eval sample `setup/` trees or vendored plugin text.
- Harness files (`CLAUDE.md`, `.claude/`, `AGENTS.md` and the other generated roots) are never committed.
- Commit messages and PR titles follow Conventional Commits.
- `catalog/README.md` is the human contributor guide and must agree with these rules.
- The validate and sync loop every layer shares: `playbook-validate-and-sync`.
