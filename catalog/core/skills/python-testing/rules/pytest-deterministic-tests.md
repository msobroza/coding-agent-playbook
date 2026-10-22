---
id: pytest-deterministic-tests
name: Deterministic tests
description: "Give every test fresh state and fixed inputs: no shared module-level instance, no unseeded randomness, no wall-clock now() and no network, so each test passes in any order and on any machine."
version: 1
scope: scoped
globs:
  - "tests/**/*.py"
applies_if:
  has_framework: ["pytest"]
section: isolation
priority: 46
tags: [python, testing, pytest, isolation]
---

# Keep tests deterministic and independent

## Description

A test that passes alone and fails in the suite, or fails only on Mondays or only in CI, costs more than it catches. Build fresh objects in each test, inline or from a function-scoped fixture, and never mutate a shared module-level instance: the order the tests run in would then change their results. Unit tests use no unseeded randomness, no wall-clock `now()` and no network: the clock and generators come in as parameters with fixed values, and external services are faked.

## Bad Example

```python
shared_store = FakeRoomStore()  # one instance for the whole module


def test_add_room() -> None:
    add_room(shared_store, Room(id="r-1", nightly_cents=10_000))

    assert shared_store.get("r-1").nightly_cents == 10_000


def test_list_rooms_starts_empty() -> None:
    assert list_rooms(shared_store) == []  # passes or fails with the run order


def test_late_checkout_fee() -> None:
    nightly_cents = random.randint(5_000, 20_000)  # a different input on every run
    fee = late_checkout_fee_cents(nightly_cents=nightly_cents, now=datetime.now(timezone.utc))
    assert fee >= 0  # the wall clock decides which branch runs
```

## Good Example

```python
def test_add_room() -> None:
    store = FakeRoomStore()

    add_room(store, Room(id="r-1", nightly_cents=10_000))

    assert store.get("r-1").nightly_cents == 10_000


def test_list_rooms_starts_empty() -> None:
    assert list_rooms(FakeRoomStore()) == []


def test_late_checkout_after_noon_costs_half_a_night() -> None:
    at_one_pm = datetime(2026, 3, 2, 13, 0, tzinfo=timezone.utc)

    fee = late_checkout_fee_cents(nightly_cents=10_000, now=at_one_pm)

    assert fee == 5_000  # 10_000 / 2
```

## Notes

- Fixed inputs make a failure reproduce identically on every machine. Generated inputs belong to Hypothesis, which seeds, shrinks and replays its failures (pytest-hypothesis-properties); anything else uses an explicitly seeded generator.
- What stands in for the clock, the network and other services: `pytest-test-doubles`. Passing the clock in as a parameter is the python-coding skill's python-pure-core rule.
- Fixture scope decides how widely state is shared: function scope by default (pytest-fixtures).
- Environment variables, the working directory and module globals are changed through the monkeypatch fixture, which undoes them: `pytest-monkeypatch`.
- What replaces the clock, generated ids and randomness, in one table: choosing-a-test-double.md.
