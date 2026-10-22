---
id: python-function-signatures
name: Function signatures
description: "Make options keyword-only, pass values that travel together as one record, and split a function whose boolean flag selects a different algorithm."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: functions
priority: 68
tags: [python, functions, design]
---

# Keep function signatures readable at the call site

## Description

A signature is read at every call site, where `create_user("ada", True, False)` says nothing about what `True` and `False` mean. Design the header so each call explains itself and cannot be misused:

- Put options after a bare `*` so callers must name them. Boolean flags are always keyword-only.
- When a boolean flag selects a different algorithm, split the function in two instead of branching on the flag. When it only adjusts one step of the same algorithm, keep it, keyword-only.
- Parameters that always travel together (a street, city and postal code; a start and end date) become one frozen dataclass passed as one argument.
- There is no fixed parameter count; a long list is the signal that a record is missing or that the function does two things.

## Bad Example

```python
def create_user(name: str, is_admin: bool, send_welcome: bool) -> User: ...


create_user("ada", True, False)  # which flag is which?


def ship(
    order_id: str, street: str, city: str, postal_code: str, country: str, express: bool
) -> Shipment: ...


class Wallet:
    def place_order(self, amount_cents: int, is_buying: bool) -> None:
        if is_buying:  # the flag picks one of two algorithms
            self.balance_cents += amount_cents
        else:
            self.balance_cents -= amount_cents
```

## Good Example

```python
def create_user(name: str, *, is_admin: bool = False, send_welcome: bool = True) -> User: ...


create_user("ada", is_admin=True, send_welcome=False)


@dataclass(frozen=True)
class Address:
    street: str
    city: str
    postal_code: str
    country: str


def ship(order_id: str, address: Address, *, express: bool = False) -> Shipment:
    """``express`` only changes the carrier, so it stays a keyword-only flag."""
    ...


class Wallet:
    def buy(self, amount_cents: int) -> None:
        self.balance_cents += amount_cents

    def sell(self, amount_cents: int) -> None:
        self.balance_cents -= amount_cents
```

## Notes

- Telling the two kinds of flag apart: if the body is `if flag: <one procedure> else: <another>` with little shared code, the callers already know which one they want, so give each its own name. If the flag changes one argument passed down or one line, splitting would duplicate the rest.
- Accept the most abstract read-only type the body needs (`Sequence`, `Mapping`, `Iterable`) and return a concrete one; the table is in `python-abstract-inputs`.
- Defaults are immutable: `None` or an empty tuple, never `[]` or `{}` (the full rule is in `python-typing`). A default must not build an I/O collaborator either (`python-dependency-injection`).
- A parameter whose values form a closed set takes an `Enum` or a `Literal`, not a free string the body compares against.
- When a call site still reads poorly after these steps, the function probably does two things; split it by responsibility (`python-small-units`).
