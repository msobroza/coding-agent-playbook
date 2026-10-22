---
id: playbook-skill-md
name: SKILL.md
description: "Write a SKILL.md as a third-person capability sentence, a playbook block, and a short body the engine completes."
version: 1
scope: scoped
globs:
  - "catalog/**/skills/*/SKILL.md"
  - "playbook/skills/*/SKILL.md"
  - "src/*/resources/skills/*/SKILL.md"
applies_if:
  playbook_layer: true
section: skills
priority: 41
tags: [playbook, skills]
---

# Write the SKILL.md the engine composes from

## Description

Frontmatter:

- `id`: equals `name` and the directory name; kebab case, at most 64 characters.
- `description`: one third-person capability sentence ending with a period; it does not start with I, you, we or use, and holds no "Use when".
- `playbook:` block: `use_when` (the condition only; the engine adds "Use when"), `files` (at most 80 characters, no trailing period: the skill's line in the always-loaded "Where guidance lives" map), `sections` and `references`.

The engine composes the listed description as `<description> Covers <active section titles>. Use when <use_when>.`, at most 300 characters with every declared section counted.

Body: a `# Title`, a short intro (what the skill is for and its scope), a `## Quick Reference`, and `## See Also` naming related skills in plain text. After it the engine appends "How to use this skill", the rules index grouped by section and "References and examples".

## Bad Example

```markdown
---
id: acme-billing
name: Billing
description: "Use when editing billing code."
playbook:
  use_when: "Use when editing billing code"
---

# Billing

## Rules

- acme-decimal-amounts
- [Rounding guide](references/rounding.md)
```

The description opens with "Use when", `name` differs from the id, `use_when` repeats the engine's words, and the body lists rule ids and its own references, which the engine already renders.

## Good Example

```markdown
---
id: acme-billing
name: acme-billing
description: "Conventions for Acme billing code and invoice data."
playbook:
  use_when: "editing billing, invoicing or payment code"
  files: "Billing and invoicing modules"
  sections:
    - id: money
      title: "Money"
      impact: HIGH
      summary: "Amounts are exact decimals in one currency per value."
      open_when: "Adding or changing an amount, a currency field, rounding or a tax computation."
---

# Acme billing

How Acme code computes, stores and shows money and invoices. Payment
provider integrations live in the acme-payments skill.

## Quick Reference

- Amounts are decimals with a currency, never floats.
- Round once, at the invoice line, half-even.

## See Also

- acme-payments: provider calls and webhooks.
```

## Notes

- The body names no rule id, holds no template syntax, no markdown link and no URL; the composed file stays under 500 lines.
- Every description is listed on every turn, so budgets are tight. In the engine, core descriptions total at most 2,800 characters on the standard probe and 3,400 on the Domino probe; core plus each bundled plugin at most 7,000 and 7,500.
- A skill without a `playbook:` block (a plugin skill) takes no rules and carries its own "Use when" in its description.
- The 300-character composition is a validate check in every layer; the description lint is an engine test over core only.
- skill-template.md has a complete SKILL.md.
