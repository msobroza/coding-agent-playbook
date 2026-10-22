---
id: docs-page-kinds
name: Page kinds
description: "Write each docs page as one kind (tutorial, how-to guide, reference or explanation), follow the repo's docs tree and link between kinds instead of mixing them."
version: 1
scope: scoped
globs:
  - "docs/**"
  - "*.rst"
section: user-docs
priority: 64
tags: [python, docs]
---

# One kind per docs page

## Description

User documentation serves four different needs, and a page that tries to serve two serves neither. Give every page exactly one kind:

- **Tutorial**: a linear lesson for a newcomer that ends in a working result. Every step is concrete and runs; theory is kept to what the next step needs.
- **How-to guide**: the steps to reach one goal, for a reader who already knows the basics. It starts from the goal ("Export orders to Parquet"), not from a feature.
- **Reference**: complete and exact descriptions of the public API, CLI or configuration. It is generated from docstrings by the repo's docs tool, not written by hand.
- **Explanation**: background, design reasons and trade-offs, read away from the keyboard.

Follow the docs tree and the navigation the repo already has: put a new page next to pages of its kind, and register it where the repo's toctree or nav lists them. When a page needs material of another kind, link to the page that holds it.

## Bad Example

A "Getting started" page that mixes all four kinds and never reaches a working result:

```markdown
# Getting started

Install the package, then read how the cache works: entries are keyed by a
content hash and evicted by an LRU policy, because ...  (two screens of design)

## OrderClient(base_url, timeout, retries, cache_dir, ...)
## OrderClient.fetch(order_id, *, fields=None, refresh=False)
## Exporter(...)                          (every parameter of three classes)

To export orders, you could also ...      (ends here, nothing ran)
```

## Good Example

The same material split by kind, each page in its place:

```text
docs/
├── tutorial/first-export.md     tutorial: install, fetch one order, export it
├── how-to/export-parquet.md     how-to: one goal, for a reader who knows the basics
├── reference/client.md          reference: generated from the docstrings
└── explanation/caching.md       explanation: why the cache keys by content hash
```

The tutorial's first steps, each runnable and each ending in a visible result:

```markdown
1. Install the package: `pip install my-pkg`, then check it with
   `python -c "import my_pkg; print(my_pkg.__version__)"`.
2. Fetch one order from the bundled sample data: `my-pkg fetch A-1 --sample`
   prints `A-1  3 items  42.00 EUR`.
3. Export it: `my-pkg export A-1 --sample --format csv` writes `A-1.csv`.
```

## Notes

- A decision record is an ADR, not an explanation page (docs-record-why).
- The README is an entry point that links into these pages, not a fifth kind that holds all four (docs-readme-essentials).
- A new feature usually needs a how-to guide plus its reference entry; change the tutorial only when the first-run path changes.
- The reference build belongs to the repo's tool: where the repo uses Sphinx or MkDocs, this skill's API reference rule for that tool says how to register a new module.
- Ask who reads the page and what they need right now; the answer picks the kind.
- The which-document reference of this skill maps a reader's need to the page kind.
