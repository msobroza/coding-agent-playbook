---
id: playbook-skill-files
name: Skill files
description: "Ship only rules, listed references, stdlib scripts and complete examples in a skill directory."
version: 1
scope: scoped
globs:
  - "catalog/**/skills/*/references/**"
  - "catalog/**/skills/*/scripts/**"
  - "catalog/**/skills/*/examples/**"
  - "playbook/skills/*/references/**"
  - "playbook/skills/*/scripts/**"
  - "playbook/skills/*/examples/**"
  - "src/*/resources/skills/*/references/**"
  - "src/*/resources/skills/*/scripts/**"
  - "src/*/resources/skills/*/examples/**"
applies_if:
  playbook_layer: true
section: skills
priority: 42
tags: [playbook, skills]
---

# List every file a skill ships and keep each kind in its place

## Description

A skill directory holds only `SKILL.md`, `rules/`, the references directory, `scripts/` and `examples/`. Sync renders `rules/` and copies the other three.

- **References.** Plain Markdown copied byte for byte (no template syntax, no priority), one level deep, with a table of contents above 100 lines. An engine-written navigation guide routes situations to rule ids, never repeats a rule body and stays within 120 lines.
- **Listing.** Each reference file and each example app directory has one `playbook.references` entry with `path`, `open_when` and an optional `applies_if`. A gated entry is neither listed nor written in a repo whose facts fail it. License copies are the one exemption.
- **Scripts.** Stdlib-only Python valid on 3.10, executable, printing results (JSON) for the agent to judge, exiting 2 on a usage error. Core skills ship only `.py` scripts: a shell script or a third-party CLI would be an imposed tool.
- **Examples.** A small complete app under `examples/<app>/` with its own `pyproject.toml`, its tests and a README mapping each file to the rule ids it demonstrates.

## Bad Example

```text
skills/acme-billing/
├── SKILL.md                  # playbook.references lists nothing
├── references/
│   └── guides/
│       └── rounding.md       # nested, and unlisted
└── scripts/
    └── fetch_rates.py        # imports a third-party HTTP client
```

Validate fails on the unlisted guide, the nesting breaks the one-level rule, and the script cannot run in a repo without that client.

## Good Example

```text
skills/acme-billing/
├── SKILL.md
├── rules/
│   └── acme-decimal-amounts.md
├── references/
│   └── rounding.md
└── examples/
    └── invoice-api/           # pyproject.toml, app/, tests/, README.md
```

```yaml
playbook:
  references:
    - path: references/rounding.md
      open_when: "Choosing where and how an amount is rounded."
    - path: examples/invoice-api
      open_when: "Wiring the billing rules into a small web app end to end."
      applies_if:
        any_framework: [fastapi]
```

## Notes

- Rules name a reference by its bare file name and an example file as examples/<app>/<file>, in plain text in their Notes.
- In the engine, examples run in a dedicated CI job from their own pyproject (the engine gains no dependency), ruff lints scripts and examples at a Python 3.10 target, and script tests live under tests/core_skills/<skill>/ using core_skill_root().
- License copies for vendored text sit in the references directory, unlisted (`playbook-third-party-content`).
- skill-template.md has a script skeleton and a guide skeleton.
