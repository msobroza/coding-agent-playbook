---
id: mkdocs-docs-build
name: MkDocs build
description: "After editing docs, mkdocs.yml or documented code, run the repo's MkDocs build strictly, as CI does, and fix each warning; never deploy inside a change."
version: 1
scope: scoped
globs:
  - "mkdocs.yml"
  - ".readthedocs.y*ml"
applies_if:
  has_file: ["mkdocs.yml"]
section: docs-build
priority: 69
tags: [python, docs, mkdocs]
---

# Build the MkDocs site as CI does

## Description

After editing `docs/`, `mkdocs.yml` or documented API, run the repo's build the way CI runs it: `mkdocs build --strict`, which the docs check also runs, or the repo's own make, nox or tox target. Without `--strict`, warnings scroll past locally and fail in CI.

Fix each warning at its cause:

- a link to a missing page or anchor;
- a page outside the `nav`, where the repo's `validation` settings warn about it;
- an identifier the API plugin cannot import.

Where the repo has a link check, run it too, and report a dead external link instead of ignoring it.

## Bad Example

```bash
mkdocs build                 # no --strict: passes here, fails in CI
git add site/                # build output committed
mkdocs gh-deploy             # the live site replaced from a feature branch
```

## Good Example

CI's command, the warning and the corrected relative link:

```bash
mkdocs build --strict
```

```text
WARNING -  Doc file 'how-to/export.md' contains a link 'reference/order.md', but the target 'how-to/reference/order.md' is not found among documentation files.
```

```markdown
See the [orders reference](../reference/orders.md) for every option.
```

## Notes

- The `validation` and plugin settings are the contract (python-tooling's static-checks rule, python-static-checks): loosening them is proposed to the user, never done to pass a build.
- The engineering documents under docs/adr, docs/specs, docs/plans, docs/research and docs/agents stay out of the published site with `exclude_docs`; propose the entry once if it is missing, because pages outside the nav are still built and published.
- The commit-time check and the docs CI job are `docs-check-in-ci`.
- Deploying the site is publishing and needs the user.
- Docs dependencies come from the repo's own docs extra, dependency group or requirements file, and are installed only with the user's agreement.
