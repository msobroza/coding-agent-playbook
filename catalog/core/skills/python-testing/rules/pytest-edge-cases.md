---
id: pytest-edge-cases
name: Edge cases
description: "Test each operation beyond the happy path: empty and zero inputs, boundaries and the values around them, invalid input, duplicates, not-found and collaborator failures."
version: 1
scope: scoped
globs:
  - "**/test_*.py"
  - "**/*_test.py"
  - "**/tests/**/*.py"
  - "**/conftest.py"
  - "**/fakes.py"
applies_if:
  has_framework: ["pytest"]
section: coverage
priority: 62
tags: [python, testing, pytest, coverage]
---

# Test the Edge Cases, Not Only the Happy Path

## Description

Bugs cluster at the edges: the empty list, the zero quantity, the value exactly at a limit, the record that does not exist. For any operation, walk the categories below and add a case for each one that applies.

| Category | Examples |
| --- | --- |
| Empty or zero | empty list, zero quantity, empty string, `None` where the signature allows it |
| Boundary | first and last item, exactly at a limit, and the values just below and above it |
| Invalid | missing required field, negative number, wrong unit |
| Duplicate | creating the same entity twice, retrying the same command |
| Not found | reading, updating or deleting an id that does not exist |
| Overflow | the largest allowed amount, a very long string |

## Bad Example

```python
def test_create_booking() -> None:
    rooms = FakeRoomStore([Room(room_id="room-1", nightly_rate_cents=10_000)])
    request = BookingRequest(room_id="room-1", check_in=date(2026, 1, 1), nights=3)

    booking = create_booking(request, rooms=rooms)

    assert booking.price_cents == 30_000  # the only case: zero nights and a bad room never run
```

## Good Example

```python
@pytest.fixture
def rooms() -> FakeRoomStore:
    return FakeRoomStore([Room(room_id="room-1", nightly_rate_cents=10_000)])


@pytest.mark.parametrize(
    ("nights", "price_cents"),
    [
        pytest.param(0, 0, id="zero-nights"),
        pytest.param(1, 10_000, id="one-night"),
        pytest.param(29, 290_000, id="below-the-limit"),
        pytest.param(30, 300_000, id="at-the-limit"),  # MAX_NIGHTS is 30
    ],
)
def test_booking_price_at_the_boundaries(
    rooms: FakeRoomStore, nights: int, price_cents: int
) -> None:
    request = BookingRequest(room_id="room-1", check_in=date(2026, 1, 1), nights=nights)

    assert create_booking(request, rooms=rooms).price_cents == price_cents


@pytest.mark.parametrize(
    ("room_id", "nights", "error", "message"),
    [
        pytest.param("room-1", 31, BookingError, "at most", id="above-the-limit"),
        pytest.param("no-such-room", 1, RoomNotFoundError, "no-such-room", id="not-found"),
    ],
)
def test_booking_is_rejected(
    rooms: FakeRoomStore, room_id: str, nights: int, error: type[Exception], message: str
) -> None:
    request = BookingRequest(room_id=room_id, check_in=date(2026, 1, 1), nights=nights)

    with pytest.raises(error, match=message):
        create_booking(request, rooms=rooms)
```

## Notes

- For each threshold, test the value itself plus the values just below and just above it; add inputs that land on a rounding half.
- Per operation, cover: the happy path; computed values with known inputs and literal expectations; not-found as the domain's own error carrying the id, never `KeyError`; a partial update that leaves the omitted fields unchanged; duplicates; and the same operation on populated data, not only on an empty store.
- Time boundaries: due exactly today, UTC midnight versus local midnight, month ends, leap days and daylight-saving changes for local-time rules, with the clock passed in (pytest-deterministic-tests).
- Invalid transitions: returning something that is not on loan, cancelling a booking twice.
- Partial failure: the second write fails and nothing is committed. Collaborator failure: a failure fake raises the collaborator's specific error, and the operation propagates or translates it as designed.
- Variations of one behavior go in a case table (pytest-parametrize); a coverage report shows which branches still miss a case (pytest-branch-coverage, where the repo measures coverage).
