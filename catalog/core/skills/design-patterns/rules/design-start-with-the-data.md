---
id: design-start-with-the-data
name: Start with the data
description: "Fix the record shapes first: a field prefix, parallel lists or a long parameter list is a missing type, and functions and classes follow from it."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: smells
priority: 61
tags: [python, design, data]
---

# Start with the data

## Description

The shape of the data decides most of a design's quality. Most cohesion and coupling problems trace back to a missing or misshapen record: fields that share a prefix are a type nobody extracted, so every function that needs that group takes several arguments, and the class holding them takes on a second job. Fix the data first, then revisit the functions and classes around it; many function and class smells disappear on their own.

## Bad Example

```python
@dataclass
class Order:
    customer_name: str
    customer_address: str
    customer_city: str
    customer_email: str
    items: list[LineItem] = field(default_factory=list)


def shipping_label(customer_name: str, customer_address: str, customer_city: str) -> str:
    return f"{customer_name}\n{customer_address}\n{customer_city}"
```

## Good Example

```python
@dataclass(frozen=True)
class Customer:
    name: str
    address: str
    city: str
    email: str

    def shipping_label(self) -> str:
        return f"{self.name}\n{self.address}\n{self.city}"


@dataclass
class Order:
    customer: Customer
    items: list[LineItem] = field(default_factory=list)
```

## Notes

- Order of work: the records first, then the functions that compute over them, then the classes that guard state. A review scans in the same order.
- Data-shape signals: fields sharing a prefix (smell id prefixed-field-group) become a record; parallel lists indexed together become one list of records; a chain of attribute reads (`order.customer.address.city`) asks for a method on the object in the middle.
- A function that needs many parameters from one object is far from its data: move it onto the record, or pass the record (design-tell-dont-ask).
- Raw structures with operations scattered around them (a nested list as a board, a dict as an account) become a domain class that keeps the data and its operations together.
- Records are typed dataclasses, never dicts. How a record is shaped (frozen, slots, derived values as properties, parallel lists merged) is python-coding's python-data-shapes; this rule decides that a record is missing.
