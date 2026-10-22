---
id: docs-changelog
name: Changelog
description: "Write changelog input through the repo's own mechanism (hand-kept file, news fragments or conventional commits), for users, with breaking changes marked."
version: 1
scope: scoped
globs:
  - "CHANGELOG*"
  - "CHANGES*"
  - "HISTORY*"
  - "NEWS*"
  - "changelog.d/**"
  - "newsfragments/**"
section: repo-files
priority: 61
tags: [python, docs, changelog]
---

# Changelog through the repo's mechanism

## Description

Find the mechanism before writing anything:

- **A hand-kept changelog**: an Unreleased section at the top, with the groups Added, Changed, Deprecated, Removed, Fixed and Security, and versions that follow Semantic Versioning.
- **News fragments**: a `[tool.towncrier]` table and its fragments directory; each change adds one fragment file, and the release tool assembles them.
- **Generated from commits** (commitizen, release-please, semantic-release): the curated input is the conventional commit message, and the generated sections are never edited by hand.

Whatever the mechanism, an entry is written for users, not for the diff: what changed for them, what they must do, a clear mark on a breaking change, and the issue it closes. The Unreleased section carries no date; a release heading carries the version and the ISO date, and is written only when releasing.

## Bad Example

```markdown
## [Unreleased] - 2026-03-04

- fixed stuff (a1b2c3d)
- refactor
```

A dated Unreleased heading, entries no user can act on, and, in a commitizen repo, the same line typed by hand inside the generated block.

## Good Example

A hand-kept changelog:

```markdown
## [Unreleased]

### Changed

- **Breaking:** `report build` takes `--output` instead of `--out`.
  Rename the flag in your scripts (#412).

### Deprecated

- `load_orders(path=...)` is deprecated; pass the path positionally.

### Fixed

- Totals no longer drop orders placed at midnight UTC (#398).
```

The breaking rename as a news fragment, in the directory the repo's config names:

```text
changes/412.bugfix.md
`report build` takes `--output` instead of `--out`; rename the flag in your scripts.
```

And the same rename as a conventional commit in a commitizen repo:

```text
fix(cli)!: rename --out to --output

BREAKING CHANGE: report build takes --output; rename the flag in scripts.
Refs: #412
```

## Notes

- A repo with no changelog gets none created: report the gap to the user.
- Refactors and test-only changes get no entry unless the repo's convention says so.
- A deprecation is listed under Deprecated and, in code, warns with `DeprecationWarning` and `stacklevel=2`.
- Version bumps happen at release time through the repo's tool, not in a feature change.
- Where the repo uses commitizen, the `commit-message-convention` playbook hook checks the message format.
