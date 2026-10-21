---
id: playbook-guardrails
name: playbook-guardrails
description: Holds the full text of every guardrail this repository enables, with what each lifecycle hook checks and on which assistants it is enforced. Use when a guardrail line in AGENTS.md needs detail, or before deleting files, committing, pushing, adding a dependency or handling secrets.
---

# Playbook guardrails

Each section is one guardrail this repository enables: the practice, then where a lifecycle hook enforces it. Where no hook runs, apply it yourself.

Committed documentation is checked by `playbook docs-check`, the `playbook-docs` pre-commit hook: when a commit stages `*.md`, `*.rst`, `docs/**` or `mkdocs.yml`, it checks the relative links and Python code blocks of the changed Markdown, then runs only the docs build, doctests and linters this repository configures. Run it yourself before committing documentation (`playbook docs-check <files>`); fix what it reports instead of skipping the hook. `[guardrails.docs] mode = "off"` in `.coding-agent-playbook.toml` switches it off.
