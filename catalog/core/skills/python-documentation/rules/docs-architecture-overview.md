---
id: docs-architecture-overview
name: Architecture overview
description: "Keep docs/architecture.md a one-page map of components, entry points, data flow and constraints, updated when a top-level package or entry point changes."
scope: scoped
globs:
  - "docs/architecture.md"
section: design-records
priority: 44
tags: [python, docs, architecture]
---

# Architecture overview

## Description

docs/architecture.md is the map a new reader opens first, linked from the README. It holds:

- the purpose of the system in two or three sentences;
- one ASCII or Mermaid diagram of the main components and the direction of their dependencies;
- one line per top-level package or service saying what it owns;
- the entry points: CLI, app factory, workers, scheduled jobs;
- the main data flow and the external systems it talks to;
- the cross-cutting constraints, each linking the ADR that explains it.

It names modules, never line numbers, which go stale with the next edit. It changes in the same change that adds, renames or removes a top-level package, an entry point or an external system, or that changes the dependency direction.

## Bad Example

A 150-line "Architecture" section inside the README:

```markdown
## Architecture

- src/orders/api.py (lines 1-240): routes
- src/orders/legacy_sync.py (lines 1-80): sync job
- ... one line per file, 140 more
```

It lists every file with line numbers, buries the README's quick start, and still names `legacy_sync`, removed two releases ago.

## Good Example

An excerpt of docs/architecture.md:

```markdown
# Architecture

Orders takes orders over HTTP, charges them through the payment provider
and exports a daily report.

    api ──> services ──> domain
              │
              └──> adapters ──> Postgres, payment provider

| Package  | Owns                                          |
| -------- | --------------------------------------------- |
| api      | HTTP routes, request and response schemas     |
| services | use cases; one transaction per call           |
| domain   | orders and money rules; imports nothing above |
| adapters | database and provider clients                 |

Entry points: `orders.api:create_app`, the `orders-export` CLI, the nightly
export job. Payments are retried only on 503 (adr/0007-retry-only-on-503.md).
```

And the README's pointer:

```markdown
How the code is organized: docs/architecture.md.
```

## Notes

- The layers and import direction the overview describes are enforced by the python-architecture skill (arch-dependency-direction, arch-one-layout-axis).
- When the file is missing, propose creating it instead of inventing one inside an unrelated change.
- Keep it to about a page: depth belongs in explanation pages under docs/ or in ADRs (`docs-record-why`).
- The file's path follows the repo's layout (`docs-document-layout`).
