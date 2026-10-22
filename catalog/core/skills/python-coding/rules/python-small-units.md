---
id: python-small-units
name: Small units
description: "Keep each function to one job in about 4 to 20 lines and each file under about 500 lines, ideally 200 to 300."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: shape
priority: 40
tags: [python, readability]
---

# Keep units small

## Description

A function does one thing, and most functions fit in about 4 to 20 lines. A file stays under about 500 lines, ideally 200 to 300. Small units are easier to name, test, review and change, whoever reads them. For a coding agent the gain is concrete too: a small unit arrives whole in one read, so all of it is reasoned about at once, while a long one is read in pages and understood in fragments, each fragment costing attention. Keep each unit of meaning the size of one read.

## Bad Example

```python
def import_orders(path: Path, repository: OrderRepository) -> int:
    imported = 0
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            # parse
            order_id = row["id"].strip()
            quantity = int(row["quantity"])
            unit_price = Decimal(row["unit_price"])
            # validate
            if not order_id:
                raise InvalidOrderRowError(f"empty id in row {row!r}")
            if quantity <= 0:
                raise InvalidOrderRowError(
                    f"{order_id}: quantity must be positive, got {quantity!r}"
                )
            # compute
            total = unit_price * quantity
            if quantity >= BULK_THRESHOLD:
                total -= total * BULK_DISCOUNT
            # write
            repository.save(Order(id=order_id, quantity=quantity, total=total))
            imported += 1
            # ... and so on: logging, retries and reporting take it to about 60 lines
    return imported
```

## Good Example

```python
def import_orders(path: Path, repository: OrderRepository) -> int:
    orders = [parse_order(row) for row in read_rows(path)]
    for order in orders:
        repository.save(order)
    return len(orders)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_order(row: Mapping[str, str]) -> Order:
    order_id = row["id"].strip()
    quantity = int(row["quantity"])
    if not order_id:
        raise InvalidOrderRowError(f"expected a non-empty id, got {row!r}")
    if quantity <= 0:
        raise InvalidOrderRowError(f"{order_id}: expected a positive quantity, got {quantity!r}")
    total = order_total(Decimal(row["unit_price"]), quantity)
    return Order(id=order_id, quantity=quantity, total=total)


def order_total(unit_price: Decimal, quantity: int) -> Decimal:
    total = unit_price * quantity
    return total - total * BULK_DISCOUNT if quantity >= BULK_THRESHOLD else total
```

## Notes

- Split along the steps: each named step does one thing, and the top function reads as the list of steps; `python-early-return` keeps each function at one level of abstraction.
- The numbers are guides, not limits. A 25-line function that does one thing is fine; a 12-line one that parses, validates and writes is not.
- Split a file past about 500 lines along its responsibilities; design-single-responsibility (design-patterns skill) says how to find them.
- The clean-code-metrics-nonregression hook blocks a change that grows a function's complexity; extracting named steps is the usual fix.
- Long data tables, exhaustive mappings and generated code are exempt: their length is data, not logic.
