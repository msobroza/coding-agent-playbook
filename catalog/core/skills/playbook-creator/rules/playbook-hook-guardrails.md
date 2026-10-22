---
id: playbook-hook-guardrails
name: Hook guardrails
description: "Write a hook's body and summary as the guidance an agent follows where the hook cannot run, and give a blocking hook a guard twin."
version: 1
scope: scoped
globs:
  - "catalog/**/hooks/**/HOOK.md"
  - "catalog/**/hooks/**/HOOK.md.j2"
  - "playbook/hooks/**"
  - "src/*/resources/hooks/**"
applies_if:
  playbook_layer: true
section: hooks
priority: 44
tags: [playbook, hooks]
---

# Make every hook degrade to guardrail text and a guard twin

## Description

A hook's body is its guardrail text, read wherever the hook cannot run: it becomes the hook's section of the playbook-guardrails skill, Continue's guardrail rule file and the agent_harness advisory. Its `summary` is its one line in `AGENTS.md`, and in the Claude Code rules file where Claude Code cannot run it: 1-120 characters, one line, no template syntax, keeping the point (what to run or do instead). Write the body as imperative guidance with the fix, not as a description of the mechanism.

A hook that blocks or checks something reproducible gets a **guard twin**: a command running the same judge, so pre-commit and CI enforce it without an agent session. In the engine the twin is a playbook subcommand (`playbook docs-check`, `playbook scan-secrets` and `playbook check-deps` are twins); in an overlay, a console script of its package; in `playbook/`, a script the repo runs. Wire it as a `repo: local`, `language: system` pre-commit hook filtered to the files it checks.

A lint-feedback hook names its rule in `linked_rule`: it inherits the rule's gate, globs and `lint_codes`, so its messages name where the fix lives.

## Bad Example

```markdown
---
id: acme-freeze-guard
decisions: [deny, none]
summary: >-
  This hook intercepts every pre-tool-use event for the edit and write tool classes and checks
  whether the freeze file exists before deciding.
---
```

The summary describes the mechanism, runs past 120 characters, and the empty body leaves a harness without hooks with nothing to follow.

## Good Example

```markdown
---
id: acme-freeze-guard
summary: During a release freeze, change only release notes; ask the release owner first.
---
While `RELEASE_FREEZE` exists at the repo root, do not edit files under `src/`.
Change only `CHANGELOG.md` and release notes, and ask the release owner before
anything else. Run `python tools/freeze_check.py` to see whether the freeze holds.
```

Its guard twin in `.pre-commit-config.yaml`:

```yaml
- repo: local
  hooks:
    - id: acme-freeze-check
      name: release freeze
      entry: python tools/freeze_check.py --freeze-file RELEASE_FREEZE
      language: system
      files: ^src/
```

## Notes

- `[hooks] advisory = false` turns the guardrail text off.
- In the engine every hook has a test module under tests/hook_runtime/handlers/<pack>/ and a manifest row, and every core hook with a body declares `summary`.
- The document-layout guard hook and docs-check are worked examples of a guard and its twin.
- hook-template.md shows the pre-commit wiring.
