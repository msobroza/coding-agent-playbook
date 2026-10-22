---
id: playbook-rule-frontmatter
name: Rule frontmatter
description: "Write static YAML frontmatter with only the engine's keys: id, name, description and scope, plus the optional ones."
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
priority: 23
tags: [playbook, rules]
---

# Use only the engine's frontmatter keys

## Description

A rule's frontmatter is static YAML, parsed before any template runs. Required: `id`, `name`, `description`, `scope`. Optional: `version`, `section`, `skill`, `globs`, `applies_if`, `priority`, `tags`, `lint_codes`. Any other key (`impact:`, `title:`, `see:`) is a validation error naming the file and the allowed keys.

| Key | What it drives |
| --- | --- |
| `name` | A short topic label; with `description`, the rule's index row |
| `description` | One actionable sentence: the index row `<name>: <description>` and Continue's pull-in line |
| `scope` | `always` (every turn) or `scoped` (delivered through a skill), lowercase |
| `section` | A section id of the owning skill; required on every rule of a sectioned skill |
| `skill` | Only on a rule in another layer's `rules/` that joins a skill with a `playbook:` block |
| `priority` | An int 0-99 (default 50), inside the section's band when the skill has sections |
| `globs` | The skill nudge on the first edit of a matching file, and Continue's attachment |
| `applies_if` | The gate on detector facts (`playbook-rule-gates`) |
| `lint_codes` | `{warn, when}`: ruff codes a linked lint hook reports against this rule, as warnings only |
| `version` | Bumped on a breaking change |

A rule inside `skills/<x>/rules/` is a member of `<x>` by its directory: it never declares `skill:`.

## Bad Example

```markdown
---
id: acme-invoice-ids
impact: HIGH
skill: acme-billing
scope: Scoped
description: "Invoice ids for {{ project_name }}"
---
```

`impact` is no engine key (the section sets it), `skill:` is redundant inside the skill's `rules/`, `Scoped` is not a scope, `name` is missing, and the description holds template syntax that is never rendered.

## Good Example

`playbook/skills/acme-billing/rules/acme-invoice-ids.md`:

```markdown
---
id: acme-invoice-ids
name: Invoice ids
description: "Generate invoice ids from the ledger sequence, never from timestamps."
version: 1
scope: scoped
section: ledger
priority: 21
globs: ["src/billing/**/*.py"]
applies_if:
  any_dependency: [sqlalchemy]
tags: [billing]
---
```

## Notes

- An always rule (`scope: always`) has no `skill`, `section` or `globs`, stays a few bullets because it is in every turn's context, and lives in the layer's `rules/` (core: `rules/always/NN-<id>.md`).
- In the engine's core layer, add no new lint_codes until the pilot ends.
