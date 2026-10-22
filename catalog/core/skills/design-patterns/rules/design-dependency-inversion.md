---
id: design-dependency-inversion
name: Dependency inversion
description: "Type a volatile collaborator as an abstraction its consumer owns, a Callable alias or a small Protocol, so the consumer stops depending on the implementation's module."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: abstractions
priority: 45
tags: [python, design, solid]
---

# Dependency inversion

## Description

Dependency injection and dependency inversion are different things. Injection is the mechanism: pass a dependency in instead of creating it inside, which already makes code testable. Inversion is the principle: type that dependency as an abstraction the consumer owns, so the consumer is also freed from the implementation's module. Inversion requires injection, but injection does not require inversion: a class that receives a concrete class is injected and still coupled to it. Use injection wherever I/O happens, and add inversion where the implementation is volatile or must be faked.

## Bad Example

```python
from vendor_sms.client import SmsAuthorizer  # the consumer imports the detail


class PaymentProcessor:
    def __init__(self, authorizer: SmsAuthorizer) -> None:  # injected, still coupled
        self._authorizer = authorizer

    def pay(self, payment: Payment) -> None:
        if not self._authorizer.authorize_by_sms(payment.customer_phone):
            raise PaymentNotAuthorizedError(payment.id)
        payment.capture()
```

## Good Example

```python
# payments.py: the consumer declares the abstraction it needs, beside itself.
Authorize = Callable[[Payment], bool]


class PaymentProcessor:
    def __init__(self, authorize: Authorize) -> None:
        self._authorize = authorize

    def pay(self, payment: Payment) -> None:
        if not self._authorize(payment):
            raise PaymentNotAuthorizedError(payment.id)
        payment.capture()


# main.py: the entry point picks the concrete function and passes it, uncalled.
processor = PaymentProcessor(authorize=sms_authorize)
```

## Notes

- Do not put `__init__` in a Protocol: different implementations need different constructor arguments.
- Protected variations: a controller that depends on a view Protocol (`bind_add_product`, `update_product_list`) works with any UI toolkit, and the toolkit can change without touching it.
- Which collaborator gets a port at a layer boundary is arch-ports in the python-architecture skill; choosing between `Callable`, Protocol and ABC is python-protocols in the python-coding skill; passing collaborators in, and when an abstraction is worth adding at all, is `python-dependency-injection`.
