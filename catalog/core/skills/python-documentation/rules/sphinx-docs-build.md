---
id: sphinx-docs-build
name: Sphinx build
description: "After editing docs or documented code, run the repo's Sphinx build the way CI does and fix each new warning instead of suppressing it."
scope: scoped
globs:
  - "docs/conf.py"
  - "docs/Makefile"
  - ".readthedocs.y*ml"
applies_if:
  has_file: ["docs/conf.py"]
section: docs-build
priority: 68
tags: [python, docs, sphinx]
---

# Build the Sphinx docs as CI does

## Description

A docs bug is a code bug, and the build is how it shows. After editing a docs page, a documented docstring or `conf.py`, run the repo's Sphinx build the way CI runs it: its make, nox or tox target, or `sphinx-build` with CI's flags. The docs check runs `-W --keep-going`; CI may add `-n` (nitpicky) or another builder, and a local run without those flags passes what CI fails.

Fix each new warning at its cause:

- an unresolved reference: a role names an object that was renamed or removed;
- an autodoc import failure: the module no longer imports, or a dependency is missing from the docs environment;
- a duplicate label, or a document that is in no toctree.

Where the repo has a link-check builder, run it too, and report a dead external link instead of ignoring it.

## Bad Example

```bash
sphinx-build docs docs/_build/html      # no -W: 3 warnings scroll past, CI fails
```

```python
# conf.py: the warnings made to go away instead of fixed
suppress_warnings = ["ref.python", "toc.not_included"]
```

```bash
git add docs/_build                     # build output committed
```

## Good Example

CI's own command, one warning and its fix:

```bash
sphinx-build -W --keep-going -n -b html docs docs/_build/html
```

```text
docs/how-to/export.rst:14: WARNING: py:func reference target not found: shop.export_csv
```

```rst
Call :func:`shop.exports.write_csv` to export the selected orders.
```

The function moved to `shop.exports` and was renamed; the role now names it, and the build is clean again.

## Notes

- Settings are the contract (python-tooling's static-checks rule, python-static-checks): `suppress_warnings`, `nitpick_ignore` and `linkcheck_ignore` entries are proposed to the user as a settings change, never added to pass a build.
- Docs dependencies come from the repo's own docs extra, dependency group or requirements file, and are installed only with the user's agreement.
- The engineering documents under docs/adr, docs/specs, docs/plans, docs/research and docs/agents stay out of the user build through `exclude_patterns`; propose the entry once if it is missing (with MyST they are read and warn as orphans).
- The doctest builder runs only where the repo already uses it; running examples is `docs-runnable-examples`.
- The commit-time check and the docs CI job are `docs-check-in-ci`.
- Publishing to a docs host is not part of the change.
