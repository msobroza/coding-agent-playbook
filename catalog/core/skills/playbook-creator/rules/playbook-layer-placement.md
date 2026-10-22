---
id: playbook-layer-placement
name: Layer placement
description: "Put each artifact in the kind directory of the one layer that owns it, never in generated output."
version: 1
scope: scoped
globs:
  - "catalog/**"
  - "playbook/**"
  - "src/*/resources/**"
applies_if:
  playbook_layer: true
section: layers
priority: 21
tags: [playbook, layers]
---

# Put each artifact in its layer's kind directory

## Description

Content reaches an agent only from a layer's kind directories; sync renders them into each harness's generated files. The four layer roots, in merge order:

1. `catalog/core/`: the engine's core, synced into every repo.
2. `catalog/plugins/<name>/`: a bundled plugin, opt-in. Core and bundled plugins are both changes to the engine repository.
3. `<package>/resources/`: an overlay package's layer.
4. `playbook/`: the consumer repo's own layer; `mkdir playbook` starts one.

Inside any root, the path says the kind:

| Kind | Path inside the layer root |
| --- | --- |
| Always rule, or a rule joining another layer's skill | `rules/<file>.md` (core keeps only `rules/always/NN-<id>.md`) |
| Member rule | `skills/<skill>/rules/<id>.md`, beside that skill's `SKILL.md` |
| Skill | `skills/<id>/`: `SKILL.md`, `rules/`, the references directory, `scripts/`, `examples/` |
| Prompt | `prompts/<id>.md` or `.md.j2` |
| Hook | `hooks/<category>/<id>/HOOK.md` (the category folder means nothing) |
| Eval sample | `eval_samples/<id>/`, beside the layer's `prompts/` |

## Bad Example

A team convention typed into generated output:

```text
AGENTS.md                                   <- edited by hand
.claude/skills/python-coding/rules/acme-retry-budget.md   <- written by hand
```

The next `playbook sync` overwrites both, and the guard-generated-outputs hook refuses the edit in the first place.

## Good Example

The same convention, and the rest of a repo's own layer:

```text
playbook/
├── rules/
│   └── acme-retry-budget.md          # joins a core skill: skill: python-coding
├── skills/
│   └── acme-billing/
│       ├── SKILL.md                  # with a playbook: block
│       └── rules/
│           └── acme-invoice-ids.md   # a member rule, found by its directory
├── prompts/
│   └── acme-release-review.md
└── hooks/
    └── release/
        └── acme-freeze-guard/
            └── HOOK.md
```

## Notes

- Pick the layer by audience: every repo is a change to core; an opt-in workflow is a bundled plugin; one organization is an overlay; one repo is `playbook/`.
- A `skills/<skill>/rules/` directory needs a `SKILL.md` with a `playbook:` block beside it, or validate fails.
- A scoped rule placed directly in core's `rules/` fails validate with a hint naming the skill directory to move it to.
- Files at a layer root (`README.md`, `LICENSE`, `ATTRIBUTIONS.md`) ship but never sync, so nothing links to them.
- Generated roots (`.claude/`, `.opencode/`, `.agents/`, `.continue/`, `AGENTS.md`, the agent_harness tree) are never edited by hand.
- Content never goes into the engine's Python package; it lives in a layer.
- After placing a file, run the loop in `playbook-validate-and-sync`.
- Skeletons for each kind: rule-template.md and plugin-template.md.
