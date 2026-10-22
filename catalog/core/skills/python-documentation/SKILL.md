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

This skill covers the prose documentation of a Python repo: the README, the changelog, the contributing guide, the citation file, the pages under docs/, and the design records that keep the reasons behind the code. Docstrings belong to the python-coding skill; this skill names them where they matter and never repeats their guidance. Every command comes from the repo's own docs tool, CI job and package manager, and no docs tool, theme, host, test runner or pre-commit hook is added unless the user asks. Engineering documents follow one layout: the default paths shown in the rules, unless the repo's committed playbook config renames them.

## Quick reference

Before finishing a change that touches public behavior:

- Public names carry the docstrings the python-coding skill asks for.
- Every prose place that states the changed behavior (README, docs pages, examples, CONTRIBUTING) changed in the same diff.
- Every edited example runs as written: through the repo's doctest command where it collects doctests, by hand once otherwise.
- The changelog input follows the repo's own mechanism: a hand-kept file, news fragments or conventional commit messages.
- `playbook docs-check` passes and, where the repo builds its docs, the build runs the way CI runs it.

## See also

- python-coding: docstrings, and why-comments inside function bodies.
- python-tooling: run the checks the way CI runs them.
- python-architecture: the layers and import direction that docs/architecture.md describes.
