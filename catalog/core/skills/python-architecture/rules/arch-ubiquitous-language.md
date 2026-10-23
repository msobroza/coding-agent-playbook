---
id: arch-ubiquitous-language
name: Ubiquitous language
description: "Name domain records, fields, use cases and tests with the terms the business experts use, and rename the code when their terms change."
version: 1
scope: scoped
globs:
  - "**/domain/**/*.py"
  - "**/models/**/*.py"
  - "**/entities/**/*.py"
  - "**/domain.py"
  - "**/models.py"
  - "**/services/**/*.py"
  - "**/application/**/*.py"
section: domain
priority: 44
tags: [python, architecture, ddd]
---

# Name domain code in the business's own words

## Description

Developers and the people who know the business need one shared vocabulary: the same term for the same concept, in conversation and in code. When the code says `start_date` and `end_date` while everyone else says check-in and check-out, every requirement has to be translated before it can be implemented, and misunderstandings creep in at each translation. Use the domain's terms for records, fields, use cases, errors and tests, everywhere from the domain package to the test names.

## Bad Example

```python
@dataclass(frozen=True)
class Reservation:  # the hotel staff say "booking"
    room_id: int
    start_date: date  # they say "check-in"
    end_date: date  # they say "check-out"


def make_reservation(
    rooms: RoomRepository, room_id: int, start: date, end: date
) -> Reservation: ...
```

## Good Example

```python
@dataclass(frozen=True)
class Booking:
    room_id: int
    check_in: date
    check_out: date


def book_room(rooms: RoomRepository, room_id: int, check_in: date, check_out: date) -> Booking: ...


def test_booking_ends_on_the_check_out_day() -> None: ...
```

## Notes

- Bind model and code early: start from a crude prototype of one concept and refine both together, instead of writing requirements for months.
- When the experts' terms change, rename the code in the same change, so the vocabulary never forks.
- Walk through scenarios with the model ("what happens when a guest checks out early?"); the questions surface concepts the code is missing.
- Folders that mirror the product's own concepts let anyone locate code by reasoning about the product.
- General naming (vague names, verbs, symmetric names) is the design-patterns skill's design-name-for-intent rule; this rule covers only the domain terms shared with the experts.
