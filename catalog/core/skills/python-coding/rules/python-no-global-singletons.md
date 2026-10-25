---
id: python-no-global-singletons
name: No global singletons
description: "Never expose services, clients or mutable configuration as module-level singletons, lazy get_x() globals or service locators; build them once and inject them."
scope: scoped
globs:
  - "**/*.py"
section: effects
priority: 50
tags: [python, design, di]
---

# Avoid global singletons and module-level shared instances

## Description

Do not expose services, clients or mutable configuration as module-level singletons that any code can import and use. Lazy `get_*()` globals and `__new__`-based singletons look convenient, but they hide coupling, make tests depend on their order, and block alternate implementations (fakes, per-tenant configuration, a second connection). Construct each dependency once, at the entry point (`main`, the app factory or its lifespan), and pass it in through constructors or parameters (`python-dependency-injection`).

- No class-based singletons: no metaclass instance cache and no caching `__new__`.
- No service locator or global registry queried from business code.
- No lazy accessor such as `get_db()` that fills a module global on first call, and no module-level client instance that business code imports as a locator.

## Bad Example

```python
_db: Database | None = None


def get_db() -> Database:  # lazy global: callers cannot inject a fake
    global _db
    if _db is None:
        _db = Database(os.environ["DATABASE_URL"])
    return _db


class OrderService:
    def place(self, order: Order) -> None:
        get_db().save(order)  # hidden dependency


class Config:  # a caching __new__: global state with extra steps
    _instance: "Config | None" = None

    def __new__(cls) -> "Config":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance


email_client = SmtpEmailClient(os.environ["SMTP_HOST"])  # eager global used as a locator
```

## Good Example

```python
class OrderService:
    def __init__(self, db: OrderStore, email: EmailClient) -> None:
        self._db = db
        self._email = email

    def place(self, order: Order) -> None:
        self._db.save(order)
        self._email.send(order.customer_email, "Order confirmed")


def main() -> None:  # the graph is built once, at the process boundary
    settings = load_settings()
    service = OrderService(
        db=SqlOrderStore(settings.database_url),
        email=SmtpEmailClient(settings.smtp_host),
    )
    service.place(load_order())
```

## Notes

- Fine at the process boundary, when not imported as a service API: module-level loggers and constants, read-only settings loaded once in `main` and passed in, logging configured once at startup, and the framework's app object that you still inject into handlers.
- A shared resource (a DB pool, an HTTP session) is created in the entry point or the app's lifespan and injected as one shared object; business code never re-fetches it through a global accessor.
- Prefer explicit teardown (`close()`, a `with` block, an async lifespan) over immortal process-wide objects that tests cannot reset.
- Web apps build the DB engine in the app factory or lifespan; scripts and CLIs may still build it at import time.
- A request-scoped `ContextVar` is an explicit exception to "no module-level state".
- Patching module globals in tests is a signal the design should use injection instead.
- Where and how the entry point wires the graph is `arch-composition-root`; an existing DI container stays there, out of business modules.
