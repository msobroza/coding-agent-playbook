---
id: python-classes-and-protocols
name: Classes and protocols
description: "Give each class one reason to change; pick the lightest construct, composition before inheritance, substitutable subtypes, small interfaces, and abstractions only once earned."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: classes
priority: 61
tags: [python, design, oop]
---

# Python classes and protocols

A class earns its place when it keeps state together with the behavior that protects it. These conventions keep classes small, replaceable and honest about their contracts.

## One reason to change

- Warning signs: describing the class needs the word "and", its module imports from unrelated layers, or its private helpers form groups around different attributes.
- Split along those lines, so each part can be tested on its own.

## The lightest construct

- A function before a class.
- A dataclass for a record; `python-data-shapes` owns how records are shaped.
- A plain class for behavior that owns state.
- Never a class that only wraps one function: call the function.

## Attributes, then properties

Attributes before getters and setters, and cheap properties, are covered in `python-properties`.

## Composition first

- Prefer composition over inheritance: keep a collaborator in an attribute and delegate to it.
- Inherit only when every subclass can stand in for its base everywhere the base is used.
- Use a mixin only for a small piece of behavior that is independent of the rest of the class.
- Framework base classes (`BaseModel`, `BaseSettings`, `DeclarativeBase`, Django views), exception hierarchies and documented ABC extension points are normal subclassing; the house-style rule to wrap rather than subclass a third-party class does not apply to them.

```python
class InvoiceArchive:  # good: holds the store it needs
    def __init__(self, store: BlobStore) -> None:
        self._store = store

    def save(self, invoice: Invoice) -> None:
        self._store.put(f"invoices/{invoice.number}.json", invoice.to_json())


class ArchivingBlobStore(LocalBlobStore):  # avoid: inherits every method it never needed
    def save_invoice(self, invoice: Invoice) -> None: ...
```

## Protocol or ABC

Choosing between a `Callable` alias, a small role-named Protocol and an ABC is covered in `python-protocols`.

## Substitutable subtypes

- A subtype accepts at least what its base accepts, promises at least what its base promises, and raises only the errors the base contract names.
- A subclass method that raises `NotImplementedError`, or base code that inspects the type of `self`, shows the hierarchy is wrong: split the interface, or switch to composition.

## Small interfaces

Split a Protocol when implementers leave methods stubbed out, or when its callers use two separate halves of it. Do not split one before either sign appears.

## Extension points

- When new variants keep arriving, replace a growing `if`/`elif` chain, or a `match` on a kind, with a mapping of strategies or an injected implementation.
- With one or two variants that rarely change, keep the branch.

```python
FeeRule = Callable[[Parcel], Decimal]

FEE_RULES: Final[Mapping[Carrier, FeeRule]] = {
    Carrier.POSTAL: postal_fee,
    Carrier.COURIER: courier_fee,
    Carrier.FREIGHT: freight_fee,
}


def shipping_fee(parcel: Parcel) -> Decimal:
    return FEE_RULES[parcel.carrier](parcel)
```

## Abstractions earn their place

- Give each piece of duplicated knowledge a single home.
- Code that merely looks alike but changes for different reasons stays separate.
- Add no parameters, options or hooks for needs nobody has stated.
- Extract a shared abstraction when the third real case arrives, not before.
