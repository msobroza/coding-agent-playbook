---
id: python-coding
name: python-coding
description: "Line- and function-level Python conventions."
playbook:
  use_when: "writing, changing or reviewing Python code"
  files: "Any Python file"
  sections:
    - id: errors
      title: "Error handling"
      impact: CRITICAL
      summary: "Catch narrowly, never swallow an exception, derive domain errors from one base and translate them once at the boundary."
      open_when: "Code adds or changes try/except, raise, an exception class, or where a failure becomes an exit code or log line."
    - id: shape
      title: "Code shape"
      impact: HIGH
      summary: "Small units and shallow nesting, so each unit fits in one read."
      open_when: "Writing or growing a function, class or module, adding a nesting level, or a file passing about 300 lines."
    - id: types
      title: "Names, types, docs"
      impact: HIGH
      summary: "Annotate every signature precisely, name callable and identifier types, accept abstract inputs, and document public names with an intent line and a usage example."
      open_when: "Naming a module, class, function or variable, writing a signature or annotation, or a public docstring."
    - id: effects
      title: "Effects and resources"
      impact: HIGH
      summary: "Inject I/O collaborators, keep business logic pure, bind resources to with blocks, and give outbound calls timeouts and bounded retries."
      open_when: "Code opens a file, connection or client, builds SQL, calls a remote service, reads the clock or keeps module state."
    - id: async
      title: "Asyncio"
      impact: HIGH
      summary: "Run independent awaits together, give every task an owner, bound fan-out and total wait, and stream with async generators."
      open_when: "Code adds or changes async def, await, create_task, gather, a TaskGroup, a semaphore or an async for loop."
    - id: pydantic
      title: "Pydantic validation"
      impact: HIGH
      summary: "Validate untrusted data once where it enters, declare constraints in the model, and load configuration into one typed settings object."
      open_when: "Code adds a Pydantic model, Field, validator, serializer or BaseSettings, or parses external JSON or environment config."
    - id: classes
      title: "Classes and data shapes"
      impact: MEDIUM
      summary: "Model records as dataclasses, type seams with small Protocols, prefer attributes and properties to getters, and use Enums for closed sets."
      open_when: "Code declares a dataclass, Protocol, ABC, Enum, property or getter, or uses a dict, long tuple or bare string as a record."
    - id: functions
      title: "Control flow"
      impact: MEDIUM
      summary: "Flatten nesting with guard clauses, end every match with a raising fallback, keep signatures short, and build small callables with partial, closures and decorators."
      open_when: "A function nests ifs over two deep, takes a bool flag or many parameters, or uses match, a decorator, partial or lambda."
    - id: idioms
      title: "Idioms and performance"
      impact: MEDIUM
      summary: "Follow the small house idioms and import conventions, pick collections by their dominant operation, and write comprehensions, generators and str.join where they read best; measure before trading clarity for speed."
      open_when: "Code writes an import statement, a file path, an f-string, a membership test, a dict .get, or a loop that builds a list or string."
  references:
    - path: references/python-version-idioms.md
      open_when: "The requires-python floor changes, or code uses a form newer than it: TaskGroup, Self, StrEnum, PEP 695, except*."
    - path: references/choosing-a-data-shape.md
      open_when: "A new value needs a type and the shape is open: dataclass, frozen, NamedTuple, TypedDict, Pydantic, Enum or NewType."
    - path: references/error-flow.md
      open_when: "A failure must cross functions or layers and it is unclear where to raise, translate, catch, log or retry it."
---

# Python coding

Python coding standards for code that stays correct, readable and maintainable: line- and function-level conventions for this repo, including validating untrusted input with Pydantic where the repo uses it. The always-loaded Python house style keeps its rules; each rule in this skill owns one other topic, with its reasons and examples.

## Quick Reference

### Error handling

```python
class ConfigError(AppError):  # every domain error derives from the project base error
    """The configuration file is missing or invalid."""


try:
    config = parse_config(path)
except ConfigParseError as exc:
    raise ConfigError(f"invalid configuration in {path!r}") from exc


def main() -> int:
    try:
        start_application()
    except AppError:
        logger.exception("Application startup failed")
        return 1  # explicit non-success outcome at the process boundary
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### Idioms and performance

Measure before trading clarity for speed; these forms are chosen because they read best.

```python
# A comprehension for one simple transform or filter
overdue_ids = [invoice.id for invoice in invoices if invoice.is_overdue]

# A generator passed straight to its consumer
total = sum(line.amount for line in lines)

# .get only for keys whose absence is normal; index required keys
timeout = options.get("timeout", DEFAULT_TIMEOUT)
customer_id = payload["customer_id"]

# A frozenset built once for membership tests
BLOCKED_REGIONS: frozenset[str] = frozenset({"region-a", "region-b"})
is_blocked = order.region in BLOCKED_REGIONS

# str.join for many parts
label = ", ".join(tag.name for tag in tags)
```

### Asyncio

```python
# Python 3.11 and later: one task group, one deadline for the group
async with asyncio.timeout(settings.quote_deadline_seconds):
    async with asyncio.TaskGroup() as group:
        invoices_task = group.create_task(billing.fetch_invoices(customer_id))
        limit_task = group.create_task(credit.fetch_limit(customer_id))

# Python 3.10: gather under one wait_for
invoices, limit = await asyncio.wait_for(
    asyncio.gather(billing.fetch_invoices(customer_id), credit.fetch_limit(customer_id)),
    timeout=settings.quote_deadline_seconds,
)

# A client opened in an async with block, with a timeout from settings
timeout = aiohttp.ClientTimeout(total=settings.http_timeout_seconds)
async with aiohttp.ClientSession(timeout=timeout) as session:
    report = await fetch_report(session, report_id)

# Fan-out bounded by a semaphore sized from settings, built on the running loop
semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
async with semaphore:
    await carrier.quote(parcel)
```

### Dependencies and control flow

```python
# Dependency injection: collaborators come in as parameters
class InvoiceService:
    def __init__(self, store: InvoiceStore, send: SendInvoice) -> None:
        self._store = store
        self._send = send


# Early return: guard clauses first, the main logic unindented
def ship(order: Order | None) -> Shipment:
    if order is None:
        raise OrderNotFoundError("order is missing")
    if not order.lines:
        raise EmptyOrderError(order.id)
    return Shipment.for_order(order)
```

### Documentation

```python
def create_user(email: str, name: str, *, send_welcome: bool = True) -> User:
    """Create a user account and optionally send the welcome email.

    Example:
        >>> user = create_user("ada@example.com", "Ada", send_welcome=False)
        >>> user.name
        'Ada'
    """
```

### Validation

```python
from pydantic import BaseModel, EmailStr, Field


class CreateUserRequest(BaseModel):
    email: EmailStr  # needs the pydantic[email] extra
    age: int = Field(ge=0, le=150)
```

### Classes and data shapes

```python
# A dataclass for a record; money is Decimal, never float
@dataclass(frozen=True)
class InvoiceLine:
    description: str
    unit_price: Decimal
    quantity: int


# A small, role-named Protocol at a seam
class InvoiceSender(Protocol):
    def send(self, invoice: Invoice) -> None: ...


# A computed property instead of a getter
@property
def full_name(self) -> str:
    return f"{self.first_name} {self.last_name}"
```

## Pythonic rewrites

| Smell | Replace with |
| --- | --- |
| An ABC hierarchy that only types a seam | A small `Protocol` (structural typing) |
| A single-method abstract class | A role-named `Callable` type alias |
| Deep class inheritance or mixins | Composed collaborators typed by a `Protocol` (design-patterns skill) |
| A wrapper class that only holds configuration | `functools.partial` or a closure |
| Factory class hierarchies | Functions, closures or `partial` (design-patterns skill) |
| A long if/elif that switches behavior | Pass the behavior in as a function (design-patterns skill) |
| An if/elif that picks what to create | A `dict[str, Callable]` registry (design-patterns skill) |
| Notification side effects written inline | Publish an event to subscribed handlers (design-patterns skill) |
| One algorithm duplicated across classes | A free function that takes a `Protocol` parameter (design-patterns skill) |
| `try`/`finally` for resource cleanup | A context manager |
| A hand-written `__init__` on a data holder | `@dataclass` |
| Bare string constants for options | An `Enum`, or `StrEnum` from Python 3.11 |

## See Also

- python-testing: tests for the code these rules shape.
- python-tooling: ruff, mypy and the test runner's settings that check these conventions.
- design-patterns: class design, responsibilities and the pattern rewrites named above.
- python-architecture: layers, ports and where each piece of code goes.
- web-application: web backends, where its rules win over this skill's where they overlap.
- ml-data: arrays, data frames and models.
