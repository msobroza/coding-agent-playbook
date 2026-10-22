---
id: python-dependency-injection
name: Dependency injection
description: "Pass I/O collaborators in as parameters; pick concrete implementations in one composition root per entry point."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: effects
priority: 48
tags: [python, design, di]
---

# Python dependency injection

A class that builds its own database session, HTTP client or mailer can only be tested or reconfigured by patching. Receive collaborators from the caller, and choose the concrete ones in a single place per entry point.

## Inject whatever does I/O

- Collaborators that reach outside the process (DB session, HTTP client, mailer, object storage, filesystem) arrive as constructor or function parameters. Constructing one inside `__init__` or a business function is a defect.
- Annotate the parameter with what the consumer needs: a role-named `Callable` alias for a single behavior, or a small `Protocol` declared in the consuming module when several methods are used.
- Add that abstraction only at a real seam: an external system, a test fake, or two or more implementations. A single in-process collaborator can be injected as its concrete type, and an existing ABC hierarchy that works can stay.

## One composition root per entry point

- Concrete implementations are chosen in exactly one place per entry point: `main()`, the web app factory or its lifespan and dependency providers, or the root CLI group. A CLI root builds services and hands them to subcommands through its context object; subcommands never construct clients.
- Wiring modules may create an engine, a session factory, the app or a router at import time, since none of those opens a connection. Business code never imports them, and nothing connects, opens a session or calls the network at import time.
- No class-based singletons (metaclass instance caches, a caching `__new__`) and no service locator or global registry queried from business code. Module-level loggers and constants are fine.
- No lazy accessor such as `get_db()` that fills a module global on first call, and no module-level client instance that business code imports as a locator. Build a shared pool, session or HTTP client in the composition root or the app's lifespan, and inject it. Process-wide things that are fine: logging configured once at startup, read-only settings loaded in `main`, and the framework's app object.

## Configuration

- Load the typed settings object once, in the composition root, and fail at startup when a required value is missing. Business code never imports a module-level settings instance.
- Prefer handing a callee the few values it uses (a base URL, a timeout) over the whole settings object.

## Tests

Tests assemble their own small root from named fakes (`FakeMailer`) passed through the same parameters production uses. Needing to patch module globals, or to reset shared state between tests, means a dependency is still hidden.

```python
SendReceipt = Callable[[Order], None]


class Checkout:  # good: the caller decides how receipts are sent
    def __init__(self, send_receipt: SendReceipt) -> None:
        self._send_receipt = send_receipt


class LegacyCheckout:  # avoid: hidden I/O, testable only by patching
    def __init__(self) -> None:
        self._mailer = SmtpMailer(host="smtp.internal")
```
