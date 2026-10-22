---
id: python-documentation
name: python-documentation
description: "Documentation practice for Python repos, using the repo's own docs tools."
playbook:
  use_when: "changing public behavior or writing a README, changelog, docs page, ADR or why-comment"
  files: "README, changelog, CONTRIBUTING, CITATION.cff and docs/ pages"
  sections:
    - id: in-sync
      title: "Docs in sync"
      impact: HIGH
      summary: "Prose docs and examples change with the behavior they describe, and every example runs as written."
      open_when: "A change alters public behavior, a default, a CLI flag, a config key or a setup step, or edits a doc example or doctest."
    - id: design-records
      title: "Design records"
      impact: HIGH
      summary: "Reasons are written where a reader looks: a comment for a local reason, an ADR for a decision, every document at its path in the repo's layout."
      open_when: "A why-comment, ADR, spec, plan, glossary entry or research note is written, or a top-level package or entry point changes."
    - id: repo-files
      title: "Repository files"
      impact: MEDIUM
      summary: "README, changelog, contributing guide and citation file stay accurate and follow the repo's own mechanisms."
      open_when: "README, CONTRIBUTING, CITATION.cff, a changelog or a news fragment is created or edited, or a release is prepared."
    - id: user-docs
      title: "User docs"
      impact: MEDIUM
      summary: "Each user-facing page is one kind, and the API reference is generated from docstrings by the repo's docs tool."
      open_when: "A tutorial, how-to, reference or explanation page is added, moved or split, or a new public module needs reference docs."
    - id: docs-build
      title: "Docs build"
      impact: MEDIUM
      summary: "The docs check and the docs build run as the pre-commit hook and CI run them, and new warnings are fixed, not silenced."
      open_when: "`playbook docs-check`, the docs build or a link check fails or warns, or conf.py, mkdocs.yml or a docs CI job changes."
---

# Python documentation

This skill covers the prose documentation of a Python repo: the README, the changelog, the contributing guide, the citation file, the user docs under docs/ and the design records that explain why the code is shaped the way it is. Docstrings belong to python-coding's docstring rule; this skill names that rule where docstrings matter and never repeats it. Every command comes from the repo's own docs tool, CI job and package manager, and no docs tool, theme, host, doctest runner or pre-commit hook is added unasked. Engineering documents follow one layout: the default paths unless the repo's `[layout]` table renames them.

## Quick reference

Before finishing a change that touches public behavior or its docs:

- Docstrings of new or changed public names follow python-coding's docstring rule.
- Every prose doc and example that states the changed behavior changed in the same diff.
- Edited examples run: through the repo's doctest command where it has one, by hand otherwise.
- Changelog input goes through the repo's own mechanism (a hand-kept file, news fragments or commit messages).
- `playbook docs-check` passes and, where the repo builds docs, the build runs as CI runs it.

## See also

- python-coding: docstrings and why-comments inside code.
- python-tooling: run the checks the way CI runs them, and fix findings instead of loosening the settings.
- python-architecture: the layers and import direction the architecture overview describes.
