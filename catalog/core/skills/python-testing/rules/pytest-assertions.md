---
id: pytest-assertions
name: Assertions that can fail
description: "Assert exact expected values that wrong output would break, add a case that tells plausible wrong implementations apart, and pin raised errors by type and a stable part of the message."
version: 1
scope: scoped
globs:
  - "tests/**/*.py"
applies_if:
  has_framework: ["pytest"]
section: structure
priority: 45
tags: [python, testing, pytest, structure]
---

# Write assertions that can fail

## Description

Every assertion must be able to fail on wrong output. `is not None`, `len(result) > 0` or a bare `assert result` pass for almost any implementation, so the test runs the code without checking it. Prefer `== expected` with a literal, and pick inputs that tell plausible wrong implementations apart: one input often cannot distinguish `x * 2` from `x + 2`, an off-by-one or swapped arguments. A raised error is pinned by its type and a stable part of its message.

## Bad Example

```python
def test_double() -> None:
    assert double(2) == 4  # x + 2 also gives 4


def test_search_returns_results() -> None:
    results = search_rooms(FakeRoomStore(rooms=[]), city="Lisbon")

    assert results is not None  # any list passes, even the wrong one
    assert len(results) > 0


def test_missing_room_raises() -> None:
    with pytest.raises(Exception):  # any error passes, even a typo's NameError
        read_room("r-404", FakeRoomStore())
```

## Good Example

```python
def test_double() -> None:
    assert double(2) == 4
    assert double(3) == 6  # x + 2 gives 5: the second case tells them apart


def test_search_returns_only_rooms_in_the_city() -> None:
    store = FakeRoomStore(rooms=[Room(id="r-1", city="Lisbon"), Room(id="r-2", city="Porto")])

    results = search_rooms(store, city="Lisbon")

    assert [room.id for room in results] == ["r-1"]


def test_missing_room_raises_not_found() -> None:
    with pytest.raises(RoomNotFoundError, match="r-404"):
        read_room("r-404", FakeRoomStore())
```

## Notes

- Not-found is a domain error (`RoomNotFoundError`), never a bare `KeyError` leaking out of a dict.
- `match=` is a regular expression searched in the message: pin a stable part (the id, the field), not the whole sentence.
- Don't test Python itself: asserting that a dataclass stores the value it was given checks the language, not your code. Test the computed values.
- Compare floats with `pytest.approx`; arrays and data frames have their own assertions in the ml-data skill.
- ruff's PT011 (`pytest.raises` too broad) and PT018 (a composite `assert a and b`) are reported under the `pytest` rule; this rule is their fix.
