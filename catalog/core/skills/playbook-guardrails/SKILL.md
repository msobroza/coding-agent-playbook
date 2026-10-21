---
id: playbook-guardrails
name: playbook-guardrails
description: Holds the full text of every guardrail this repository enables, with what each lifecycle hook checks and on which assistants it is enforced. Use when a guardrail line in AGENTS.md needs detail, or before deleting files, committing, pushing, adding a dependency or handling secrets.
---

# Playbook guardrails

Each section is one guardrail this repository enables: the practice, then where a lifecycle hook enforces it. Where no hook runs, apply it yourself.

Where this repository wires the `playbook-docs` (or `coding-agent-playbook-docs`) pre-commit hook and `[guardrails.docs] mode` is not `"off"`, committed documentation is checked by `playbook docs-check`: when a commit stages `*.md`, `*.markdown`, `*.rst`, anything under `docs/`, `mkdocs.yml`, `mkdocs.yaml` or `doc/conf.py`, it checks the relative links and Python code blocks of the changed Markdown, then runs only the docs build, doctests and linters this repository configures. There, run it yourself before committing documentation (`playbook docs-check <files>`) and fix what it reports instead of skipping the hook.
