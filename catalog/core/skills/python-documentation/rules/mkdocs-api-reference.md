---
id: mkdocs-api-reference
name: MkDocs API reference
description: "Where mkdocs.yml enables an API plugin, write identifier blocks instead of copied signatures and give each new public module its block and nav entry."
scope: scoped
globs:
  - "mkdocs.yml"
  - "docs/**"
applies_if:
  has_file: ["mkdocs.yml"]
section: user-docs
priority: 66
tags: [python, docs, mkdocs]
---

# MkDocs API reference from docstrings

## Description

Where `mkdocs.yml` enables an API plugin (mkdocstrings), reference pages hold identifier blocks such as `::: package.module` and the plugin renders the signatures and docstrings. A pasted signature drifts the first time the code changes.

- Match the handler's `docstring_style` to the docstring style the repo already uses.
- Give a new public module its identifier block and a `nav` entry, or let the repo's page-generation script pick it up when it has one.
- Describe behavior in prose and leave the API itself to the generated block.
- Without an API plugin, follow whatever the repo's reference pages already do, and propose a plugin only when the user asks.

## Bad Example

A reference page with a pasted signature that lost a parameter, and a new page missing from `nav`:

```markdown
# Orders

`fetch_orders(customer_id, limit=100)`: fetch the orders of a customer.
```

```yaml
nav:
  - Home: index.md
  - Reference:
      - Customers: reference/customers.md
```

The function now takes `since`, and `reference/orders.md` is built but reachable from no menu.

## Good Example

`docs/reference/orders.md` holds one identifier block:

```markdown
# Orders

::: shop.orders
```

The nav lists it, and the plugin options stay as they were:

```yaml
nav:
  - Home: index.md
  - Reference:
      - Customers: reference/customers.md
      - Orders: reference/orders.md

plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          options:
            docstring_style: google
```

## Notes

- Cross-references use the autorefs syntax only where that plugin is enabled.
- Docstrings themselves are python-coding's docstring rule (python-docstrings); the block only renders them.
- Hide private modules with the handler's filters, never by deleting their docstrings.
- Running the build and fixing its warnings is `mkdocs-docs-build`.
