---
id: playbook-skill-sections
name: Skill sections
description: "Declare a skill's sections from CRITICAL to LOW and give each member a priority inside its section's impact band."
scope: scoped
globs:
  - "catalog/**/skills/*/SKILL.md"
  - "playbook/skills/*/SKILL.md"
  - "src/*/resources/skills/*/SKILL.md"
applies_if:
  playbook_layer: true
section: skills
priority: 40
tags: [playbook, skills]
---

# Declare ordered sections and number members inside their bands

## Description

A skill with rules declares `sections:` in its `playbook:` block, ordered CRITICAL, HIGH, MEDIUM, LOW. Each section has:

- `id`: kebab case, unique in the skill; members name it in `section:`.
- `title`: one line of at most 40 characters; the composed description names it in its Covers clause.
- `impact`: CRITICAL, HIGH, MEDIUM or LOW.
- `summary`: one line saying what the section's rules require.
- `open_when`: one line (aim for 120 characters, at most 200) naming the change, construct, file or task that should make the agent open those rules. It never restates the title, and no two sections trigger on the same thing.

Keep 2-8 sections, each with at least one member. Each member names its section and takes a priority inside the section's band: CRITICAL 20-39, HIGH 40-59, MEDIUM 60-79, LOW 80-99. Number the rules of one impact from the band floor up, in index order: sections in declared order, the most important rule of each first. Validate checks only that the priority lies in the band; the numbering keeps the index readable. The index orders rules by section, then priority, then id, and shows only sections with an active rule.

## Bad Example

```yaml
playbook:
  sections:
    - id: style
      title: "Style"
      impact: LOW
      summary: "Naming and layout."
      open_when: "Style."
    - id: money
      title: "Money"
      impact: HIGH
      summary: "Amounts are exact."
      open_when: "Money."
```

LOW comes before HIGH (validate fails), each `open_when` repeats its title, and a member of `money` with `priority: 61` falls outside the HIGH band. A title written as `# Round once [HIGH]` also fails: the tag is never authored.

## Good Example

```yaml
playbook:
  sections:
    - id: money
      title: "Money"
      impact: HIGH
      summary: "Amounts are exact decimals in one currency per value."
      open_when: "Adding or changing an amount, a currency field, rounding or a tax computation."
    - id: invoices
      title: "Invoices"
      impact: MEDIUM
      summary: "Invoice ids and states follow one lifecycle."
      open_when: "Creating, numbering, voiding or reissuing an invoice, or editing its state machine."
```

A member of `money` in `skills/acme-billing/rules/acme-decimal-amounts.md`:

```yaml
section: money
priority: 40
```

## Notes

- The impact tag in each rendered rule title and index heading comes from the section.
- A rule from another layer that joins without `section:` warns and lands in an engine-made Other section, listed last.
- A declared section with no active member in a repo is simply not shown, so an empty section hides silently: give each declared section a member before the skill ships.
- Skills without sections (outside core) keep a flat index and free priorities, but a skill past about five rules reads better with sections.
- Inserting a rule renumbers the rest of its band; a band holds 20 ranks.
- skill-template.md has a full `playbook:` block with sections.
