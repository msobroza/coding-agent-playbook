# Dependency injection

## Injection and inversion are different moves

Injection means a collaborator arrives as a parameter instead of being built inside the code that uses it. Inversion means the consumer declares the abstraction it needs and the implementation conforms to it, so the source dependency points from the detail toward the policy. Injection is almost always worth it for anything that does I/O. Inversion is worth it only at a seam: an external system, a test fake, or two real implementations. Injecting a concrete class is perfectly legitimate.

## Forms, lightest first

| Form | Use when | Example |
|---|---|---|
| function parameter | one call needs the collaborator | `def close_overdue(session: Session, today: date) -> int` |
| `Callable` alias | the consumer needs a single behavior | `SendSms = Callable[[str, str], None]` |
| constructor parameter | several methods of one object share the collaborator | `ReminderJob(loans, send_sms, clock)` |
| consumer-owned `Protocol` | the consumer calls several methods | `class OverdueLoans(Protocol)` |
| ABC | implementations share code, or outside authors subclass a documented extension point | an `ExportFormat` base with a template method |

Guidelines:

- Name aliases and Protocols after the role the consumer needs (`SendSms`, `OverdueLoans`), never after an implementation.
- Declare the Protocol in the consuming module or its package's `ports.py`. Implementations satisfy it structurally and do not import it.
- Keep each Protocol as narrow as its consumer. A consumer that calls two methods gets a two-method Protocol, even when the implementation has twelve.
- `@runtime_checkable` lets `isinstance` confirm only that the method names exist, not their signatures. Do not dispatch on it.
- Never build an I/O collaborator as a default argument (`client: Client = Client()`). It is constructed once, at import, and hides the dependency. A default that is a pure function, such as a standard pricing rule, is fine.
- `functools.partial` is a quick way to pre-bind configuration. Check that your type checker still verifies the remaining parameters; where it does not, a small named function keeps the signature explicit.

## A role-named alias and a narrow Protocol

```python
SendSms = Callable[[str, str], None]  # (phone number, message)
Clock = Callable[[], datetime]


class OverdueLoans(Protocol):
    def due_before(self, day: date) -> list[OverdueLoan]: ...


def send_overdue_reminders(loans: OverdueLoans, send_sms: SendSms, clock: Clock) -> int:
    overdue = loans.due_before(clock().date())
    for loan in overdue:
        send_sms(loan.member_phone, f"Please return the {loan.tool_name}, due {loan.due_on}.")
    return len(overdue)
```

The function knows nothing about SQL, the SMS vendor or the wall clock. Production passes a SQL-backed `OverdueLoans`, the gateway's bound `send` method and `lambda: datetime.now(timezone.utc)`. A test passes a list-backed fake, a recording function and a fixed time.

## Two axes of variation

When behavior varies along two independent axes, inject one collaborator per axis instead of writing a class for every combination. A tool library's stock-take report can be rendered as CSV or JSON and delivered by email or to a shared folder. Four classes (`CsvEmailStockTake`, `JsonFolderStockTake` and so on) collapse into two parameters:

```python
Render = Callable[[Sequence[StockLine]], bytes]
Deliver = Callable[[str, bytes], None]  # (file name, content)


def publish_stock_take(
    lines: Sequence[StockLine], render: Render, deliver: Deliver, day: date
) -> None:
    deliver(f"stock-take-{day.isoformat()}", render(lines))
```

This is the bridge pattern without the class hierarchy. The composition root chooses one renderer and one delivery function. A new format or destination is one new function, not a new row of classes. When either axis needs state or several methods, promote that parameter to a Protocol; the shape stays the same.

## Anti-patterns

- **Building collaborators inside.** `self._gateway = HttpSmsGateway(...)` in `__init__` forces tests to patch and makes every caller inherit the vendor choice.
- **Service locator.** A registry or container queried from business code (`services.get(SendSms)`) hides the dependency behind a lookup. Pass parameters. If the project already uses a DI container, keep it in the composition root and keep its imports and decorators out of business modules.
- **Class-based singletons.** A metaclass or caching `__new__` that always returns one shared instance is global state with extra steps. Build one instance in the root and pass it along. Module-level loggers and constants are fine.
- **Passing the whole settings object.** A function that needs a base URL and a timeout takes those two values.
- **Injecting what never varies.** `json.dumps`, `math.ceil` or a pure domain helper does not need to be a parameter. Injection is for I/O, time, randomness and real variation points.
- **Speculative ports.** A Protocol with one implementation and no fake in the tests is indirection without payoff. Use the concrete type until a second implementation or a test needs the seam.
