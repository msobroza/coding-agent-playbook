---
id: python-dependency-injection
name: Dependency injection
description: "Pass I/O collaborators in as parameters, typed by a role-named Callable alias or a small Protocol only at a real seam."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: effects
priority: 48
tags: [python, design, di]
---

# Loose coupling with dependency injection

## Description

Instead of creating its collaborators inside, a class or function receives them from the caller. A class that builds its own database session, HTTP client or mailer can only be tested or reconfigured by patching; one that receives them can be handed a fake, a second implementation or a different configuration without changing its code.

- Whatever reaches outside the process (DB session, HTTP client, mailer, object storage, filesystem, clock) arrives as a constructor or function parameter. Constructing one inside `__init__` or a business function is a defect: look for `self.x = ConcreteClass()` in `__init__`.
- Annotate the parameter with what the consumer needs: a role-named `Callable` alias for a single behavior, or a small `Protocol` declared in the consuming module when several methods are used.
- Add that abstraction only at a real seam: an external system, a test fake, or two or more implementations. A single in-process collaborator can be injected as its concrete type, and an existing ABC hierarchy that works can stay.

## Bad Example

```python
class OrderProcessor:
    def __init__(self) -> None:
        # Hard-wired collaborators: every caller and every test inherits them
        self.db = SqlOrderStore("orders.db")
        self.mailer = SmtpMailer(host="smtp.internal")
        self.payments = CardGateway(api_key="...")

    def process(self, order: Order) -> None:
        self.payments.charge(order.total)
        self.db.save(order)
        self.mailer.send_confirmation(order.customer_email)
```

## Good Example

```python
from collections.abc import Callable
from decimal import Decimal
from typing import Protocol

SendConfirmation = Callable[[str], None]  # one behavior: a role-named alias


class OrderStore(Protocol):  # declared by its consumer, only the methods it calls
    def save(self, order: Order) -> None: ...


class OrderProcessor:
    def __init__(
        self,
        store: OrderStore,
        charge: Callable[[Decimal], None],
        send_confirmation: SendConfirmation,
    ) -> None:
        self._store = store
        self._charge = charge
        self._send_confirmation = send_confirmation

    def process(self, order: Order) -> None:
        self._charge(order.total)
        self._store.save(order)
        self._send_confirmation(order.customer_email)


def test_process_saves_and_confirms() -> None:
    store, sent = FakeOrderStore(), []
    processor = OrderProcessor(store, charge=lambda amount: None, send_confirmation=sent.append)

    processor.process(sample_order)

    assert store.saved == [sample_order]
    assert sent == [sample_order.customer_email]
```

## Notes

- Forms, lightest first: a function parameter (one call needs it), a `Callable` alias (one behavior), a constructor parameter (several methods share it), a consumer-owned `Protocol` (several methods called), an ABC (implementations share code).
- Never build an I/O collaborator as a default argument (`client: Client = Client()`): it is constructed once, at import, and hides the dependency.
- Hand a callee the few values it uses (a base URL, a timeout), not the whole settings object.
- Inject what varies: I/O, time, randomness and real variation points. `json.dumps` or a pure domain helper is called directly.
- A test passes a named fake, a recording function or `lambda: True` through the same parameter production uses; needing to patch module globals means a dependency is still hidden. Testing use cases through fakes is `arch-test-use-cases-with-fakes`.
- FastAPI dependency aliases use concrete `AsyncSession` / `httpx.AsyncClient` at the route edge; Protocols are for the app's own ports.
- Where the concrete objects are built is `arch-composition-root`; module-level singletons and service locators are `python-no-global-singletons`.
