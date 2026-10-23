---
id: arch-event-store
name: Event store
description: "Fold events with pure apply and decide functions, append with the expected stream version and reject a stale append, and never cache replay on a method."
version: 1
scope: scoped
globs:
  - "**/events/**/*.py"
  - "**/events.py"
  - "**/event_store.py"
  - "**/eventstore/**/*.py"
  - "**/domain/**/*.py"
  - "**/projections/**/*.py"
  - "**/services/**/*.py"
section: read-models
priority: 83
tags: [python, architecture, event-sourcing]
---

# Load, decide and append against the stream version

## Description

- State and decisions are pure functions: `apply` folds one event into the state; a decision function checks the rules against the state and returns new events or raises a domain error.
- The store only appends. Each event gets a sequence number within its stream, and every append states the version its decision was based on. When the stream has moved on, the store rejects the append with a concurrency error, and the caller reloads and decides again. In SQL, a unique constraint on (stream id, version) enforces it.
- Never put `functools.cache` or `lru_cache` on a method that replays events: the cache keys on `self`, keeps every instance alive and keeps serving the old state after the next append. Keep an explicit state that the append path updates, or read from a projection.

## Bad Example

```python
class Inventory:
    def __init__(self, store: EventStore) -> None:
        self.store = store

    @cache  # keeps every Inventory alive; stale unless every writer clears it
    def items(self) -> list[tuple[str, int]]:
        counts = Counter[str]()
        for event in self.store.all_events():
            counts[event.data] += 1 if event.type is EventType.ITEM_ADDED else -1
        return [(item, count) for item, count in counts.items() if count > 0]

    def add_item(self, item: str) -> None:
        self.store.append(Event(EventType.ITEM_ADDED, item))  # no expected version
        self.items.cache_clear()
```

## Good Example

```python
@dataclass(frozen=True)
class ToolState:
    on_loan_to: UUID | None = None


@dataclass(frozen=True)
class StreamHistory:
    events: tuple[ToolEvent, ...]
    version: int


def apply(state: ToolState, event: ToolEvent) -> ToolState:
    match event:
        case ToolLent():
            return replace(state, on_loan_to=event.member_id)
        case ToolReturned():
            return replace(state, on_loan_to=None)
        case _:
            assert_never(event)  # a new event type fails the type check here


class ToolEventStore(Protocol):
    def load(self, tool_id: UUID) -> StreamHistory: ...
    def append(self, tool_id: UUID, events: Sequence[ToolEvent], expected_version: int) -> None: ...


def lend_tool(
    store: ToolEventStore, tool_id: UUID, member_id: UUID, due_on: date, clock: Clock
) -> None:
    history = store.load(tool_id)
    state = reduce(apply, history.events, ToolState())
    event = lend(state, tool_id, member_id, due_on, clock())
    store.append(tool_id, [event], expected_version=history.version)
```

## Notes

- Projections are pure functions over the stream, each one standalone, so a new view needs no change to the store or to existing projections. Feed them in the write path, in the same transaction as the append, or from a subscriber that reads the log in order and records the last position it processed; either way a projection can be rebuilt by replaying from the start.
- Add snapshots only when replay time is measured to be a problem: store the stream id, version and state every N events, load the newest and replay only the later events. A snapshot is a cache: one written with an older state shape is discarded, not migrated.
- The events themselves, and when to adopt event sourcing at all, are arch-event-sourcing.
