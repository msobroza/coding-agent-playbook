---
id: docs-document-layout
name: Engineering document paths
description: "Write the glossary, ADRs, architecture overview, specs, plans, research and framework notes at their layout paths, whatever framework is enabled."
scope: scoped
globs:
  - "docs/**"
  - "CONTEXT.md"
  - "CONTEXT-MAP.md"
  - ".scratch/**"
section: design-records
priority: 43
tags: [python, docs, layout]
---

# One layout for engineering documents

## Description

Documentation lives in the same repository as the code, so each version of the code carries the documents that explain it. One layout holds those documents whatever spec-driven framework is enabled (superpowers, mattpocock, none, or an organization's own), so every agent and person finds them in the same place:

- CONTEXT.md: the glossary of domain terms; CONTEXT-MAP.md when the repo has several contexts.
- docs/adr/NNNN-slug.md: decision records.
- docs/architecture.md: the architecture overview, linked from the README.
- docs/specs/YYYY-MM-DD-slug.md: specs, designs and PRDs.
- docs/plans/YYYY-MM-DD-slug.md: plans, with their local tickets in docs/plans/YYYY-MM-DD-slug/NN-ticket.md.
- docs/research/slug.md: research notes.
- docs/agents/: framework setup notes.
- .scratch/: throwaway prototypes only, never committed.

User documentation (tutorials, how-to guides, reference, explanation) sits beside these under docs/.

## Bad Example

```text
.scratch/order-export/spec.md     a spec where a framework's own text puts it
.scratch/plan.md                  a plan where nobody will find it
decisions/use-postgres.md         an ADR outside docs/adr, with no number
```

## Good Example

```text
CONTEXT.md
docs/
├── architecture.md
├── adr/
│   ├── 0001-use-postgres.md
│   └── 0002-retry-only-on-503.md
├── specs/
│   └── 2026-03-02-order-export.md
├── plans/
│   ├── 2026-03-04-order-export.md
│   └── 2026-03-04-order-export/
│       ├── 01-csv-writer.md
│       └── 02-cli-flag.md
├── research/
│   └── export-formats.md
├── agents/
│   └── setup.md
└── how-to/
    └── export.md
```

## Notes

- A repo may rename these directories in the layout table of its committed playbook config; sync then rewrites the paths in this rule, so the paths shown are this repo's. The file name patterns never change: the ISO date the document is created, a lowercase kebab slug, the next free four-digit ADR number.
- The always-loaded document-layout rule states the layout in three lines, and the `document-layout-guard` playbook hook blocks spec or plan writes into other known locations (a framework's own folder, a spec under .scratch/) and names this repo's directory.
- A document found at another path is reported to the user, not moved, unless the user asks.
- Where the repo builds docs with Sphinx or MkDocs, these engineering directories are kept out of the user build.
- What each kind of document holds: decision records in `docs-record-why`, the overview in `docs-architecture-overview`.
- The path for each piece of writing: see which-document.md.
