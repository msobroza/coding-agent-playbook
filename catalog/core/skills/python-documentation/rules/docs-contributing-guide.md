---
id: docs-contributing-guide
name: Contributing guide
description: "Keep CONTRIBUTING's setup, test, check, docs and convention commands identical to what CI runs, and update it when a dev command or convention changes."
scope: scoped
globs:
  - "CONTRIBUTING*"
  - ".github/CONTRIBUTING*"
  - "docs/CONTRIBUTING*"
section: repo-files
priority: 62
tags: [python, docs, contributing]
---

# Contributing guide

## Description

CONTRIBUTING (at the root, in .github/ or under docs/) tells a new contributor:

- how to set up the development environment;
- how to run the tests, the lint, format and type checks, the docs check and the docs build, exactly as CI runs them;
- which branch, commit-message and PR-title conventions the repo enforces;
- where changelog input, ADRs and docs pages go.

It changes in the same change that alters a dev command, a tool, a CI job or a convention. Do not create one unasked. When asked, derive every command from the CI workflow, Makefile, noxfile, tox.ini or pyproject scripts, never from memory: a command that differs from CI's passes locally and fails in review.

## Bad Example

```markdown
## Development

    pip install -r requirements-dev.txt
    flake8 src

Open a PR when done.
```

CI runs `ruff check .` in a locked environment, the requirements file was removed, and the PR-title convention CI enforces is not mentioned.

## Good Example

```markdown
## Development

Commands below are copied from the `check` job in .github/workflows/ci.yml;
change both together.

Setup (the CI job's install step; in a uv project):

    uv sync --locked

Checks, in CI's order:

    uv run ruff check .
    uv run ruff format --check .
    uv run mypy
    uv run pytest
    uv run playbook docs-check

Conventions: commit messages and PR titles follow Conventional Commits
(`feat(cli): ...`). Changelog input is the commit message. Decisions go
in docs/adr/, user docs under docs/.
```

## Notes

- The repo's tool settings are the contract, and checks run the way CI runs them (python-static-checks, python-tooling skill).
- Write uv commands only in a uv project; otherwise copy the install step CI uses.
- A code of conduct or a security policy is a separate file this rule does not cover.
- Long explanations link to pages under docs/ instead of growing the guide.
- Where changelog input goes follows `docs-changelog`; where ADRs and specs go follows `docs-document-layout`.
