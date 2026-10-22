---
id: sphinx-api-reference
name: Sphinx API reference
description: "Generate reference pages from docstrings through the extensions conf.py already enables, register each new public module, and never copy signatures into prose."
version: 1
scope: scoped
globs:
  - "docs/conf.py"
  - "docs/**"
applies_if:
  has_file: ["docs/conf.py"]
section: user-docs
priority: 65
tags: [python, docs, sphinx]
---

# Sphinx API reference from docstrings

## Description

Reference pages are generated from docstrings through the extensions `docs/conf.py` already enables: autodoc, autosummary, napoleon or numpydoc, a type-hints extension, or autoapi. A hand-written signature drifts the first time the code changes; a generated one cannot.

- Register a new public module, class or function where the repo's index needs it: an `automodule` or `autosummary` entry, the toctree, and `__all__` when autodoc follows it.
- Never copy a signature or a parameter list into prose; describe behavior and let the generated entry state the API.
- Refer to API objects with roles such as `:func:`, `:class:` and `:mod:`, so the build reports a reference that a rename broke.
- Leave the extensions list as it is: a new extension is a settings change for the user to approve.

## Bad Example

A hand-written page that missed a new keyword argument, and a new module that never reaches the reference:

```rst
.. function:: fetch_orders(customer_id, limit=100)

   Fetch the orders of a customer.

.. autosummary::
   :toctree: generated

   shop.orders
   shop.customers
```

The function now takes `since`, and the new `shop.exports` module is missing from the list, so its reference page is never built.

## Good Example

The generated entry replaces the copied signature, and the new module joins the existing list:

```rst
Orders
======

Use :func:`shop.orders.fetch_orders` to page through a customer's orders.

.. autosummary::
   :toctree: generated

   shop.orders
   shop.customers
   shop.exports
```

`conf.py` keeps the extensions line it already had:

```python
extensions = ["sphinx.ext.autodoc", "sphinx.ext.autosummary", "sphinx.ext.napoleon"]
```

## Notes

- Keep napoleon or numpydoc settings, and a type-hints extension where conf.py enables one, matched to the docstring style the repo already uses.
- What a docstring holds, types included, is python-coding's docstring rule (python-docstrings); the reference only renders it.
- Use intersphinx roles to other projects only where conf.py enables intersphinx.
- `autodoc_mock_imports` is only for heavy optional dependencies the docs environment lacks, and it is proposed to the user as a settings change.
- Generated stub directories (such as `generated/`) follow the repo's ignore rules; never hand-edit a generated stub.
- Running the build and fixing its warnings is `sphinx-docs-build`.
