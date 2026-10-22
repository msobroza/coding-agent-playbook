---
id: python-early-return
name: Shallow nesting
description: "Keep nesting to about two levels and one level of abstraction per function, with guard clauses, early returns and extracted helpers."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: shape
priority: 41
tags: [python, readability]
---

# Keep nesting shallow

## Description

Keep each function at one level of abstraction and its nesting at about two levels. An `if` inside a `for` inside an `if` inside a `try` makes the reader track every enclosing condition at once, and buries the main logic at the deepest level. Handle edge cases first with guard clauses and an early `return`, skip items with `continue`, branch on shape with `match`, and extract an inner block into a named function. The flat version is easier for every reader to follow; for a model, the attention spent tracking nested conditions is a real cost that shows up as worse answers.

## Bad Example

```python
def checkout(order: Order) -> Receipt:
    if order.is_valid:
        if order.items:
            if order.customer.is_active:
                # main logic buried three levels deep
                total = sum((item.price for item in order.items), Decimal(0))
                discount = calculate_discount(order.customer)
                return Receipt(order_id=order.id, total=total - discount)
            else:
                raise InactiveCustomerError(order.customer.id)
        else:
            raise EmptyOrderError(order.id)
    else:
        raise InvalidOrderError(order.id)
```

## Good Example

```python
def checkout(order: Order) -> Receipt:
    # guard clauses handle the edge cases first
    if not order.is_valid:
        raise InvalidOrderError(order.id)
    if not order.items:
        raise EmptyOrderError(order.id)
    if not order.customer.is_active:
        raise InactiveCustomerError(order.customer.id)

    # the main logic is flat and clear
    total = sum((item.price for item in order.items), Decimal(0))
    discount = calculate_discount(order.customer)
    return Receipt(order_id=order.id, total=total - discount)


# loops use continue the same way; a combined check becomes a named predicate
def is_billable(fee: ShippingFee) -> bool:
    return fee.cents > 0 and not fee.waived and fee.region in BILLED_REGIONS


def post_fees(fees: Iterable[ShippingFee], ledger: Ledger) -> None:
    for fee in fees:
        if not is_billable(fee):
            continue
        ledger.post(fee)
```

## Notes

- More than two levels of nested `if`, `for`, `while`, `with` or `try` in one function is the signal to flatten it.
- Give each guard clause one condition, so the error it raises or the item it skips names exactly one reason.
- Move a condition that combines several checks into a named predicate function; the name replaces a comment.
- When a loop body needs its own guards, extract it into a per-item function so the loop stays one level deep.
- Failures raise domain errors, never status strings. Where absence is a normal outcome, a guard returns `None` or an Enum member instead.
- One level of abstraction: a function that orchestrates steps calls named helpers; it does not also parse bytes or format strings inline.
