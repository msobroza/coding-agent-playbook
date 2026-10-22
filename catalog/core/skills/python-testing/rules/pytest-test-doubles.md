---
id: pytest-test-doubles
name: pytest test doubles
description: "Double only what the code does not own: a named fake passed in like production by default, autospec only at thin third-party seams, and monkeypatch for the environment and code that cannot take a parameter yet."
version: 1
scope: scoped
globs:
  - "tests/**/*.py"
  - "**/conftest.py"
applies_if:
  has_framework: ["pytest"]
priority: 61
tags: [python, testing, pytest, mocking]
---

# pytest test doubles

A test double stands in for something slow, nondeterministic or outside the repo's control. Pick the simplest one that keeps the test honest about the real contract: a named fake first, a signature-checked patch only where no parameter exists yet.

## What to double

- Double only what the code does not own: the network, databases, clocks, randomness, third-party SDKs, and the filesystem outside `tmp_path`.
- Never double the unit under test or its own helpers. A test that replaces part of the code it checks passes whatever that part does.

## Named fakes by default

- Write a small class named for what it replaces (`FakeInvoiceStore`, `FakeShippingRates`). It keeps its state in memory, does no I/O and returns realistic data.
- Pass it through the same parameter production uses (`python-dependency-injection`), so the test exercises the real wiring.
- Assert on what the fake holds after the Act, not on the order of calls: a test pinned to call sequences breaks on every refactor that keeps the behavior.

```python
class FakeInvoiceStore:
    def __init__(self) -> None:
        self.saved: dict[str, Invoice] = {}

    def save(self, invoice: Invoice) -> None:
        self.saved[invoice.number] = invoice


def test_issue_invoice_saves_the_gross_total() -> None:
    store = FakeInvoiceStore()

    issue_invoice(store, number="INV-7", net_cents=1000)

    assert store.saved["INV-7"].total_cents == 1200  # 1000 + 20% VAT
```

## Thin third-party seams

- When the code wraps an SDK it cannot take as a parameter yet, patch the name where the code under test looks it up (`billing.gateway.Client`), not where the SDK defines it.
- Build the double with `unittest.mock.patch(..., autospec=True)` or `unittest.mock.create_autospec(...)`, so a call with the wrong signature fails, and give it return values shaped like the real ones.
- Never use a bare `Mock()` or `MagicMock()`: it accepts any attribute and any call, so a renamed method still passes.
- `unittest.mock` ships with Python. Use the `mocker` fixture only when the project already depends on the plugin that provides it.

## The `monkeypatch` fixture

- Use it for environment variables (`setenv`, `delenv`), the working directory (`chdir`), dict entries (`setitem`) and attributes of code that cannot take a parameter yet (`setattr`). It undoes every change at teardown, even when the test fails.
- Never assign to `os.environ` or to a module global directly, and never hand-write a set-then-restore: a failing test leaks the change into every test after it.
- In new code, needing a patch means a dependency is hidden. Add the parameter instead.

## Warning signs

- Many doubles in one test means the unit has too many collaborators. Report that design problem; don't mock harder.
- Time and randomness come in as a clock or a seeded generator (`python-pure-core`). Freeze-time libraries are only for characterizing legacy code that reads the clock directly.
- Overriding route dependencies in a FastAPI app belongs to `fastapi-app-wiring` (when the repo uses FastAPI).
