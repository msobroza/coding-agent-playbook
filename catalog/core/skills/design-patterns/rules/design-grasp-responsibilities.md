---
id: design-grasp-responsibilities
name: GRASP responsibilities
description: "Decide who creates an object, who handles a system event, and where behavior with no domain owner lives, with the GRASP creator, controller, indirection and pure fabrication principles."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: responsibilities
priority: 43
tags: [python, design, grasp]
---

# GRASP responsibilities

## Description

GRASP answers "where does this behavior belong?" for functions and modules as much as for classes, which suits Python. Four of its principles decide placement:

- **Creator:** let a unit create the objects it contains, records or closely uses, or the ones it has the initializing data for, so callers need not know their constructors.
- **Controller:** route a system event (a request, a CLI command, a queue message) to a thin handler that parses the input, calls one operation and maps the result or error back; it holds no business rules.
- **Indirection:** put an intermediate between two units that should not know each other.
- **Pure fabrication:** when a responsibility belongs to no domain concept, invent a unit for it instead of overloading a domain class.

## Bad Example

```python
# The caller builds Sale's internals and Payment stores itself.
line1 = SaleLineItem(product=headset, quantity=2)
line2 = SaleLineItem(product=keyboard, quantity=1)
sale = Sale(items=[line1, line2])


class Payment:
    def execute(self) -> None: ...

    def save(self, db: Connection) -> None:  # persistence inside a domain object
        db.execute("INSERT INTO payments VALUES (?)", (str(self.amount),))
```

## Good Example

```python
@dataclass
class Sale:
    items: list[SaleLineItem] = field(default_factory=list)

    def add_item(self, product: Product, quantity: int) -> None:
        self.items.append(SaleLineItem(product=product, quantity=quantity))


sale = Sale()
sale.add_item(product=headset, quantity=2)
sale.add_item(product=keyboard, quantity=1)


class TransactionStore:  # a fabrication: not a domain noun, it keeps Payment focused
    def __init__(self, db: Connection) -> None:
        self._db = db

    def save(self, record: TransactionRecord) -> None:
        self._db.execute("INSERT INTO payments VALUES (?)", (str(record.amount),))


class PaymentHandler:
    def __init__(self, store: TransactionStore) -> None:
        self._store = store

    def process(self, payment: Payment) -> None:
        payment.execute()
        self._store.save(TransactionRecord(amount=payment.amount))
```

## Notes

- Creator's exception: business objects never create collaborators that do I/O; the entry point builds them and passes them in.
- Controller: the handler holds no business rules, and the domain never imports the delivery framework.
- Indirection, with a clock passed in instead of `date.today()` inside the order:

```python
def compute_discount(customer: Customer, today: date) -> Discount:
    loyal = (today - customer.created_at).days > 365
    return Discount(rate=Decimal("0.20") if loyal else Decimal("0"))
```

- Every indirection costs the reader a hop: add one only where it cuts a real dependency. Adapter, facade, observer and mediator are indirections.
- `TransactionStore` illustrates pure fabrication only; repositories and units of work as patterns are the python-architecture skill's.
- The other GRASP principles live in their own rules: Information Expert in `design-tell-dont-ask`, low coupling in `design-low-coupling`, high cohesion in `design-single-responsibility`, polymorphism in `design-open-closed`, protected variations in `design-dependency-inversion`.
- All nine GRASP principles and the SOLID map, each with the rules that apply it: see principles-and-grasp.md.
