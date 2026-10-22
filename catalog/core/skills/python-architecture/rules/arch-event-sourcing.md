---
id: arch-event-sourcing
name: Event sourcing
description: "Use event sourcing only when history is the product; model events as frozen past-tense records with ids, plain values, a caller-supplied UTC time and a schema version."
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
priority: 82
tags: [python, architecture, event-sourcing]
---

# Source events only when history is the product

## Description

With ordinary tables you keep only the current state, so you cannot answer what the state was at 3 p.m. yesterday or which actions led to it. Event sourcing keeps an append-only log of events instead, one stream per aggregate, and computes the current state as a fold over the stream. Use it when an audit trail is mandated, temporal queries matter, several views derive from the same history, or events drive other systems; stay with ordinary tables when the current state is all you need.

- Name events in the past tense for something that happened (`ToolLent`, `ToolReturned`); an imperative (`LendTool`) is a command.
- Make events frozen dataclasses that carry ids and plain values, never ORM objects.
- Give every event an `occurred_at` that is timezone-aware UTC and supplied by the caller's clock.
- Version the payload. When its shape changes, add an upcaster that converts old payloads into the current class when they are read; never rewrite stored events.

## Bad Example

```python
class EventType(Enum):
    ITEM_ADDED = "item_added"
    ITEM_REMOVED = "item_removed"


@dataclass(frozen=True)
class Event:
    type: EventType
    data: str  # untyped payload, no version
    timestamp: datetime = field(default_factory=datetime.now)  # naive and a hidden clock
```

## Good Example

```python
@dataclass(frozen=True)
class ToolLent:
    tool_id: UUID
    member_id: UUID
    due_on: date
    occurred_at: datetime  # aware UTC, from the caller's clock
    schema_version: int = 1


@dataclass(frozen=True)
class ToolReturned:
    tool_id: UUID
    occurred_at: datetime
    schema_version: int = 1


ToolEvent = ToolLent | ToolReturned


def lend(state: ToolState, tool_id: UUID, member_id: UUID, due_on: date, now: datetime) -> ToolLent:
    if state.on_loan_to is not None:
        raise ToolOnLoanError(tool_id)
    return ToolLent(tool_id, member_id, due_on, occurred_at=now)


event = lend(state, tool_id, member_id, due_on, now=datetime.now(timezone.utc))
```

## Notes

- Costs to accept before starting: personal data inside events is hard to erase (store a reference, or encrypt it per person and delete the key on request); every consumer must handle every past event version, forever; reporting needs a projection per question.
- When the real requirement is "who changed what, and when", an audit table written in the same transaction as the ordinary rows delivers it at a fraction of the cost.
- Commands produce events: a command is intent, an event is a fact. The read side is arch-cqrs and arch-read-model-projections; in-process domain events without a log are the design-patterns skill's design-domain-events rule.
- Loading, appending and folding a stream is arch-event-store.
