---
id: playbook-rule-ids
name: Rule ids
description: "Give each rule a stable kebab-case id that equals its file name and names its owner by prefix."
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
priority: 24
tags: [playbook, rules]
---

# Keep rule ids stable, unique and prefixed

## Description

A rule id is at once the override key, the file name and the handle that prompts, hooks and lint feedback use. Write it in lowercase kebab case (`^[a-z0-9]+(-[a-z0-9]+)*$`, at most 64 characters).

- The file name minus `.md` or `.md.j2` equals the id for every rule inside a skill's `rules/`, in every layer, and for every rule of the engine's layers; an always rule may keep an `NN-` order prefix.
- Ids are unique inside a layer: two files with one id fail validate, naming both.
- The prefix names the owner: the library or tool that owns the topic (`pytest-`, `ruff-`, `mypy-`, `sqlalchemy-`, `fastapi-`, `pydantic-`), the skill family (`python-`, `design-`, `arch-`, `web-`, `ml-`, `docs-`, `domino-`, `a2a-`, `playbook-`), or an organization prefix in an overlay or `playbook/` (`acme-`), so a later engine id never collides with yours by accident.
- No rule id starts with `guardrail-`, and no hook id equals a rule or prompt id.

## Bad Example

```text
playbook/skills/acme-billing/rules/TypingRules.md     # holds id: python_typing2
```

The file name differs from the id, the id breaks the kebab-case pattern, and the unprefixed name collides with an engine id the day core ships one. Splitting a rule badly does the same damage:

```text
acme-retries.md  ->  acme-retry-count.md + acme-retry-backoff.md   # old id deleted
```

Every prompt whose `includes_rules` lists `acme-retries` now fails validate.

## Good Example

A split where the piece that keeps the topic keeps the id:

```text
acme-retries.md          # keeps the id and the retry policy
acme-retry-backoff.md    # the carved-out backoff detail, a new prefixed id
```

```yaml
includes_rules: [acme-retries]   # the prompt is unchanged
```

## Notes

- A retired id is never reused: a new rule with an old id inherits stale prompt lists and hook links (the engine pins its retired ids in tests).
- Renaming an id is a breaking change: update `includes_rules`, every `linked_rule` and the lint-code owners in the same change.
- Overlay and `playbook/` files directly under `<layer>/rules/` may keep free names, but a file name that matches the id keeps a search cheap.
- How layers merge on the id: `playbook-override-by-id`.
