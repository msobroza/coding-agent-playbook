---
id: pytest-fixtures
name: pytest fixtures
description: "Keep fixtures function-scoped unless a resource is expensive and immutable, tear down after yield, place each where its users share it, name and type it by what it returns, and return factories for variations."
version: 1
scope: scoped
skill: python-testing
globs:
  - "tests/**/*.py"
  - "**/conftest.py"
applies_if:
  has_framework: ["pytest"]
priority: 63
tags: [python, testing, pytest, fixtures]
---

# pytest fixtures

Fixtures build the world a test runs in. Keep each one narrow, typed and close to the tests that use it, so a reader sees what a test depends on without searching the tree.

## Scope

- Function scope is the default: every test gets a fresh value, so test order cannot change the results.
- Use `module` or `session` scope only for a resource that is expensive to build and effectively immutable, such as a database engine or a parsed schema. Pair it with a function-scoped fixture that resets state for each test: roll back a transaction, clear a table, re-seed a generator.

```python
@pytest.fixture(scope="session")
def ledger_engine() -> Iterator[Engine]:
    engine = create_engine(TEST_LEDGER_DSN)
    yield engine
    engine.dispose()


@pytest.fixture
def ledger_session(ledger_engine: Engine) -> Iterator[Session]:
    connection = ledger_engine.connect()
    transaction = connection.begin()
    yield Session(bind=connection)
    transaction.rollback()
    connection.close()
```

## Teardown

- Write the setup, `yield` the value, then the cleanup. pytest runs the code after `yield` even when the test fails.
- Never combine `yield` and `request.addfinalizer` in one fixture: two teardown paths make the cleanup order hard to follow.

## Placement

- In the test module when only that module uses the fixture.
- In the nearest `conftest.py` when several modules of one directory share it.
- In the root `conftest.py` only for suite-wide resources.
- Move a fixture up only when a second location needs it. Avoid redefining a fixture of the same name lower in the tree: which one a test gets then depends on where its file sits.

## Names and types

- Name a fixture after what it returns: `ledger_session` rather than `db`, `tmp_invoice_dir` rather than `tmpdir`.
- Annotate every fixture with the type it returns (`Iterator[T]` for a `yield` fixture).
- Never write `from conftest import ...`. Fixtures arrive by parameter name, and shared helpers belong in an ordinary module.

## Factories

- When tests need variations of one object, return a factory with keyword-only parameters and valid defaults, so each test states only the attributes it depends on.
- When the objects need cleanup, have the factory record what it created and remove it after `yield`.

```python
@pytest.fixture
def make_reading() -> Callable[..., SensorReading]:
    def build(*, sensor_id: str = "hall-1", celsius: float = 21.5) -> SensorReading:
        return SensorReading(sensor_id=sensor_id, celsius=celsius)

    return build


def test_alert_fires_above_the_threshold(make_reading: Callable[..., SensorReading]) -> None:
    assert needs_alert(make_reading(celsius=41.0))
```

## Variants and diagnostics

- Use `params=` on a fixture only when every test that uses it must run against each variant, such as two storage backends. Cases of a single test belong in `parametrize` (`pytest`).
- `pytest --fixtures tests/billing` lists the fixtures visible from a directory and where each one is defined. `pytest --setup-show` prints when each fixture is set up and torn down.
