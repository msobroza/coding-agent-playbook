---
id: docs-same-change
name: Docs in the same change
description: "Update every prose doc and example that states a changed behavior, flag, default, config key or setup step in the same change."
version: 1
scope: scoped
globs:
  - "README*"
  - "docs/**"
  - "examples/**"
  - "CHANGELOG*"
  - "CONTRIBUTING*"
section: in-sync
priority: 40
tags: [python, docs]
---

# Docs change with the behavior they describe

## Description

Documentation lives in the repository next to the code, so each version of the code carries the docs that match it. That only holds when both change together. A change to public behavior, a parameter, a default, an exception a caller handles, a CLI command or flag, a config key or environment variable, or an install or setup step updates every prose place that states it in the same change: the README, the pages under docs/, examples/, CONTRIBUTING and docs/architecture.md.

A diff whose docs contradict its code is unfinished. Removing a feature removes its docs too: a page or README section that still describes a deleted flag sends readers to an error.

## Bad Example

The CLI flag is renamed, and nothing else changes:

```diff
--- a/src/report/cli.py
+++ b/src/report/cli.py
-    parser.add_argument("--out", type=Path, required=True)
+    parser.add_argument("--output", type=Path, required=True)
```

The README usage block and docs/how-to/export.md still tell users to run `report build --out report.html`, which now fails.

## Good Example

Search for the old spelling first, then change every hit in the same diff:

```bash
git grep -n -e '--out' -- 'README*' docs examples
```

```diff
--- a/src/report/cli.py
+++ b/src/report/cli.py
-    parser.add_argument("--out", type=Path, required=True)
+    parser.add_argument("--output", type=Path, required=True)
--- a/README.md
+++ b/README.md
-report build --out report.html
+report build --output report.html
--- a/docs/how-to/export.md
+++ b/docs/how-to/export.md
-Pass `--out` to choose the file name.
+Pass `--output` to choose the file name.
--- a/CHANGELOG.md
+++ b/CHANGELOG.md
 ## [Unreleased]
+
+### Changed
+
+- **Breaking:** `report build` takes `--output` instead of `--out`.
+  Rename the flag in your scripts (#412).
```

The changelog hunk is the input a hand-kept changelog expects; a repo with news fragments or conventional commits takes it in that form instead (`docs-changelog`).

## Notes

- Search for the old name, flag, key or default before finishing; the search, not memory, finds the pages that mention it.
- Docstrings are the python-docstrings rule's job (python-coding skill); this rule covers prose outside the code.
- An accepted ADR is a record, not live documentation: a new ADR supersedes it and it is never rewritten (`docs-record-why`).
- Stale docs outside the change are reported to the user, not fixed in the same diff.
- Before finishing: docstrings updated (python-docstrings, python-coding skill); edited examples run (`docs-runnable-examples`); the README updated for a user-facing change (`docs-readme-essentials`); changelog input written (`docs-changelog`); the docs check passes (`docs-check-in-ci`).
- The which-document reference in this skill routes a change to every file it must touch.
