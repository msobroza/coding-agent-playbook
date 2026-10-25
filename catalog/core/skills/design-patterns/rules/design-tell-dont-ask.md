---
id: design-tell-dont-ask
name: Tell, don't ask
description: "Tell the object that owns the data to act instead of reading its fields and deciding for it; talk only to near collaborators."
scope: scoped
globs:
  - "**/*.py"
section: responsibilities
priority: 41
tags: [python, design, coupling]
---

# Tell, don't ask

## Description

Do not interrogate an object's state and then act on it from outside: tell the object to do it. Behavior belongs on the unit that holds the data it needs (Information Expert), so the object can guard its own invariants and a change to its data stays in one place. Code that reads several fields of another object to compute or change something about it (feature envy), reaches through a chain of objects, or writes another object's private attributes depends on the internals of everything it touches.

## Bad Example

```python
# Ask, then act: every caller repeats the rule and mutates the state.
if order.status is OrderStatus.OPEN:
    order.status = OrderStatus.PAID
    send_receipt(order)

# Feature envy: the total is computed far from its data.
total_cents = sum(line.unit_price_cents * line.quantity for line in order.lines)

# A chain through objects the caller does not own.
total = rental.vehicle.total_price(rental.days, rental.additional_km)
```

## Good Example

```python
@dataclass
class Order:
    lines: list[OrderLine]
    status: OrderStatus = OrderStatus.OPEN

    @property
    def total_cents(self) -> int:
        return sum(line.subtotal_cents for line in self.lines)

    def mark_as_paid(self) -> None:
        if self.status is not OrderStatus.OPEN:
            raise OrderNotOpenError(self.status)
        self.status = OrderStatus.PAID


@dataclass(frozen=True)
class RentalContract:
    vehicle: Vehicle
    days: int
    additional_km: int

    @property
    def total_price(self) -> Decimal:
        return self.vehicle.total_price(self.days, self.additional_km)


order.mark_as_paid()
send_receipt(order)
total = rental.total_price
```

## Notes

- Law of Demeter: a method talks to its parameters, its own attributes and objects it creates, not to strangers reached through them (`a.b.c.method()`). Ask the nearest object for what you need, or pass that value in directly.
- Encapsulate data-structure access: `game.scoreboard.add_point(player)` instead of `game.scoreboard.points[player] += 1`.
- Never read or write another object's `_attribute` outside its class or module (content coupling): add the method the caller needs, or move the logic into the owner. How to keep internal state private is python-hide-internal-state in the python-coding skill.
- Do not take Information Expert too far: when a computation also needs outside rules (seasonal prices, regional tax), a separate function that receives the object and the rules keeps it from growing into a god class.
- Exceptions to the Law of Demeter: fluent APIs that return the same kind of object, value objects, and data-transfer records whose structure is the contract.
- Review smell ids: feature-envy, attribute-chain, private-access.
