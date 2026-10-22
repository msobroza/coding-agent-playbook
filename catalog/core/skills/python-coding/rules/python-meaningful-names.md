---
id: python-meaningful-names
name: Meaningful names
description: "Name modules, classes, functions and variables for exactly what they are, so a search for the name finds mostly that concept."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: types
priority: 42
tags: [python, naming]
---

# Meaningful names

## Description

A name is what every reader meets first and what they search for later. A name like `data`, `process`, `handler`, `Manager` or `Service` matches dozens of unrelated places, so whoever looks for it, a person in an editor or an agent running a search, opens file after file before finding the right one, and each wrong match costs a read. A name that says exactly what the thing is, such as `RoomAvailabilityQuery`, `parse_invoice_csv` or `BookingNightsCounter`, matches a handful of places, and the first is usually the right one. Pick specific names, and keep one name for one concept across the codebase.

## Bad Example

```python
# utils.py
def process(data: list[str]) -> list[str]: ...


class Manager:
    def handle(self, item: Booking) -> int: ...

    def create_line_item(self, name: str, quantity: int) -> None:
        self.items.append(name)  # "create" promises a new item; this appends
```

A search for `process`, `Manager` or `handle` returns mostly unrelated code, and `utils` says nothing about what the module holds.

## Good Example

```python
# invoices/csv_import.py
from collections.abc import Iterable


def parse_invoice_csv(rows: Iterable[str]) -> list[InvoiceLine]: ...


class BookingNightsCounter:
    def count_nights(self, booking: Booking) -> int: ...

    def add_line_item(self, line_item: LineItem) -> None:
        self.line_items.append(line_item)
```

Each name greps to the few places that define and use it, and each verb matches what the body does.

## Notes

- The grep test: search the repo for a new name. If most results are unrelated, pick a more specific name; if only the places that matter come back, keep it.
- Generic words (data, info, item, handler, manager, service, util, helper, processor) are fine only when qualified by what they hold or do: `raw_invoice_rows`, `PaymentRetryHandler`.
- One concept, one name: once the code says `customer`, it never also says `client` or `account_holder` for the same thing; rename stray synonyms in the change that meets them.
- Verbs match behavior: `create_x` builds and returns an x, `add_x` puts an x into a collection, `get_x` retrieves one without side effects.
- Name a module after its responsibility (`csv_import.py`, `pricing.py`), never `utils.py`, `helpers.py` or `misc.py`.
- `design-name-for-intent` (design-patterns skill) covers the review angle: sibling classes that do alike things get alike method names. `arch-ubiquitous-language` (python-architecture skill) covers the domain's own vocabulary.
