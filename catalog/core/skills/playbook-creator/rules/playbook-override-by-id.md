---
id: playbook-override-by-id
name: Override by id
description: "Extend a layer with a new prefixed id; reuse an existing id only to replace that artifact whole."
scope: scoped
globs:
  - "catalog/**"
  - "playbook/**"
  - "src/*/resources/**"
applies_if:
  playbook_layer: true
section: layers
priority: 22
tags: [playbook, layers]
---

# Extend with a new id, override by reusing one

## Description

Layers merge by the frontmatter `id`, not the file name, in this order: core, then each overlay or bundled plugin in `overlays_enabled` order, then `playbook/`. A later artifact with an id that already exists replaces the earlier one whole: nothing is merged field by field. A new id adds alongside.

What follows from that:

- Prompts that include an overridden rule get the override, and linked hooks and lint feedback follow it, because the id is the handle.
- Skill membership is resolved after the merge, so a skill override keeps the skill's members, but it must keep the `playbook:` block and every section id its members name.
- Two files with one id inside one layer fail validate, naming both paths.
- Hooks differ: an overlay's hook with an existing id may only add (its builtin config merges key by key); a `playbook/` hook may replace a non-mandatory one; `[hooks] disable` switches a hook off with no file at all.

## Bad Example

Copying a core skill to add one rule:

```text
playbook/skills/python-coding/SKILL.md     # a copy of core's file, plus one line
```

The copy freezes core's description, intro and sections at today's text: every later engine update to that skill is silently shadowed, and a section dropped from the copy breaks every rule that joins it.

## Good Example

A new rule with its own prefixed id, joining the core skill:

```markdown
---
id: acme-retry-budget
name: Retry budget
description: "Cap retries per request at the budget the team agreed."
scope: scoped
skill: python-coding
section: effects
priority: 55
globs: ["src/**/*.py"]
applies_if:
  any_dependency: [httpx, requests]
---
```

Priority 55 sits inside the HIGH band (40-59) of that section. Check where it came from:

```bash
playbook render acme-retry-budget --show-source
```

## Notes

- Override only when the earlier text is wrong for this repo; keep its id so `includes_rules`, linked hooks and lint codes keep pointing at it.
- `playbook check` lists each artifact as applicable, skipped (with the failing predicate) or overriding, so an accidental override shows up there.
- An organization prefix (`acme-`) keeps a later engine id from colliding with yours by accident (`playbook-rule-ids`).
- Joining a skill from another layer takes `skill:` and `section:` (`playbook-rule-frontmatter`).
