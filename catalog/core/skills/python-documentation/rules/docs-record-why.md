---
id: docs-record-why
name: Record the why
description: "Record a hard-to-reverse decision as an ADR at docs/adr/NNNN-slug.md, supersede accepted ADRs instead of rewriting them, and put the why of a change in its commit message."
scope: scoped
globs:
  - "docs/adr/**"
section: design-records
priority: 42
tags: [python, docs, adr]
---

# Record why, where a reader looks

## Description

Code shows what it does; it cannot show why it is shaped that way, which alternatives were weighed, or what would break if it changed. Each reason goes where its reader looks for it:

- A reason tied to one line or block is a comment next to it (python-comments-why, python-coding skill).
- A choice that is hard to reverse, had a real alternative and would surprise a later reader is an architecture decision record (ADR) at docs/adr/NNNN-slug.md, with four parts: context, decision, consequences and status.
- The why of the change itself is the commit message.
- Background on why the system is shaped as it is goes in docs/architecture.md for the map and in an explanation page for depth.

An accepted ADR is a record of what was decided then, not live documentation: it is never rewritten. When the decision changes, a new ADR supersedes it, and the old one's status names its successor, so the history of the decision stays readable.

## Bad Example

A retry policy that only answers 503 errors, explained nowhere, and an old ADR edited in place:

```diff
--- a/docs/adr/0003-use-postgres.md
+++ b/docs/adr/0003-use-postgres.md
-We store orders in Postgres.
+We store orders in Postgres, and since this month events go to the queue.
```

## Good Example

A new ADR at docs/adr/0007-retry-only-on-503.md:

```markdown
# 7. Retry payment calls only on 503

Status: accepted

## Context

The provider answers 500 for declined cards and 503 when it is overloaded.
Retrying a 500 charged two customers twice (issue #412).

## Decision

Retry only 503 responses, three times with backoff; surface every other error.

## Consequences

A provider outage that returns 500 fails at once; on-call sees it immediately.
```

A superseded record keeps its text and changes only its status:

```markdown
Status: superseded by 0009-events-on-the-queue.md
```

## Notes

- ADR numbers and file names follow `docs-document-layout`.
- When the enabled framework ships its own ADR template, its headings win and the path stays docs/adr.
- A domain term goes in the glossary, CONTEXT.md, not in an ADR (`docs-document-layout`).
- Write an ADR only for a decision a later reader would question; a routine choice needs a commit message, not a record.
- A TODO carries an issue number, or it is not written.
- Suppression comments follow the always-on Python house style (name the code and say why).
- Docstrings are python-docstrings' job (python-coding skill); comments inside a body say why, never what.
