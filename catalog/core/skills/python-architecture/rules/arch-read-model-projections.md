---
id: arch-read-model-projections
name: Read model projections
description: "Build a read model with a pure projector run in the same transaction as the write, never store time-dependent values, and ship a command that rebuilds every row."
version: 1
scope: scoped
globs:
  - "**/queries/**/*.py"
  - "**/queries.py"
  - "**/read_models/**/*.py"
  - "**/projections/**/*.py"
  - "**/projections.py"
  - "**/services/**/*.py"
  - "**/application/**/*.py"
section: read-models
priority: 81
tags: [python, architecture, cqrs]
---

# Project read models in the write's transaction

## Description

A read model is a projection table maintained for one screen, worth it when the split query of arch-cqrs is still too slow or the screen needs values that are expensive per request (counts across years, a text preview, a score).

- A projector turns write-side state, or an event, into one read row, and the use case upserts it. Keep the computation a pure function, so it is tested without a database.
- Run the projector in the same transaction as the write, so readers never see a write without its projection. Run it asynchronously, from an outbox or the event log, only when write latency matters more than freshness, and then let the screen show how fresh its data is.
- Never project values that depend on the current time, such as "overdue" or "days left": store the inputs (`due_on`) and compare at query time, or the read model is wrong by tomorrow.
- Ship a rebuild command that recomputes every read row from the source of truth; the first change to the read shape needs it.

## Bad Example

```python
@router.post("/tools/{tool_id}/loans")
def lend(tool_id: UUID, body: LendRequest, lending: LendingDep, session: SessionDep) -> None:
    lending.lend_tool(tool_id, body.member_id)  # commits the loan
    refresh_tool_popularity(session, tool_id)  # a crash here leaves the view stale
```

## Good Example

```python
@dataclass(frozen=True)
class ToolPopularity:
    tool_id: UUID
    times_lent: int
    last_lent_on: date | None


def project_popularity(tool_id: UUID, lent_on: Sequence[date]) -> ToolPopularity:
    return ToolPopularity(tool_id, len(lent_on), max(lent_on, default=None))


def lend_tool(uow: UnitOfWork, tool_id: UUID, member_id: UUID, today: date) -> None:
    with uow:
        uow.loans.add(Loan(tool_id, member_id, lent_on=today))
        history = uow.loans.lent_dates(tool_id)
        uow.popularity.upsert(project_popularity(tool_id, history))
        uow.commit()  # the loan and its projection land together
```

## Notes

- A detail view of one record keeps reading the write model; project only what list and dashboard screens need.
- The rebuild command replays the same pure projector over every source row, so the projector is the one place the read shape is defined.
- An asynchronous projector records the last position it processed, so it resumes without skipping or repeating a write.
- Projections fed from an event log follow the same rules (arch-event-store).
