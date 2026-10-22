---
id: arch-make-legacy-testable
name: Make legacy code testable
description: "Make untested code testable in steps: pin its behavior, list its hidden inputs, lift each to a parameter typed with the narrowest role, move the concrete choice to the composition root, then test with fakes."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: testing
priority: 54
tags: [python, architecture, testing]
---

# Cut seams into legacy code before changing it

## Description

Code is hard to test when it builds what it needs: a session created inside the function, a module-level client, `datetime.now()`, `uuid4()`, an environment variable or a file read by path. Other blockers are I/O mixed into business logic, a complex `__init__` that connects or loads, and functions whose return type depends on the branch taken. Rewriting such code untested is a gamble; cut seams into it step by step instead:

1. **Characterize.** If nothing tests the code yet, pin its current behavior with a characterization test at the outermost seam you can call, such as the CLI command against a scratch database. Fix nothing yet.
2. **List the hidden inputs**: objects built inside the function, module globals, the clock, ids, randomness, environment variables, files.
3. **Lift each one to a parameter** typed with the narrowest role the function uses (a `Callable` alias or a small Protocol), extract pure logic from the I/O around it, and move the concrete choice up into the composition root. Update every caller in the same change.
4. **Rewrite the tests** with fakes and literal inputs, then add the cases that were impossible before: time boundaries, failures, empty results.

## Bad Example

```python
def get_room(room_id: int) -> Room:
    session = SessionLocal()  # builds its own session: no test can replace it
    row = session.get(RoomRow, room_id)
    return Room(room_id=row.room_id, number=row.number)  # a missing room: AttributeError
```

## Good Example

```python
class RoomLookup(Protocol):  # the one method get_room needs
    def get(self, room_id: int) -> Room: ...


def get_room(rooms: RoomLookup, room_id: int) -> Room:
    return rooms.get(room_id)  # raises RoomNotFoundError


# the composition root picks the implementation
def show_room(room_id: int) -> None:
    with session_factory() as session:
        render(get_room(SqlRoomRepository(session), room_id))


def test_get_room_returns_the_stored_room() -> None:
    room = Room(room_id=1, number="101")
    assert get_room(InMemoryRoomRepository([room]), 1) == room
```

An intermediate step is fine: first lift the session to a parameter (`get_room(session, room_id)`), then narrow it to a port once a fake is worth having.

## Notes

- Introduce a Protocol only at a real seam (arch-ports): a clock or an id factory needs a `Callable` alias, an in-process helper needs nothing.
- Freezing time with a library is for characterizing code that cannot accept a clock yet, never a substitute for passing one.
- Change behavior only after the seams are in and the characterization tests are green; the refactoring moves themselves are the design-patterns skill's concern, and characterization tests the python-testing skill's.
- The tests that follow are arch-test-use-cases-with-fakes; the root that now builds the concrete objects is arch-composition-root.
