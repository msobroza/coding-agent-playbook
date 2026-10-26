---
id: arch-cqrs
name: CQRS
description: "Split commands, which change state and return little, from queries, which select only the columns one screen shows, straight from SQL; add a read model only when that is still too slow."
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
priority: 80
tags: [python, architecture, cqrs]
---

# Separate commands from queries, in code first

## Description

CQRS (command query responsibility segregation) answers one problem: reads that are slow or awkward because they go through the write model. It is not a starting point. Split in code first, which costs almost nothing and fixes most slow list endpoints:

- A command is a use case that changes state, enforces the business rules and returns little beyond an id.
- A query returns read records shaped for one screen. It selects only the columns that screen shows, straight from SQL, without loading aggregates or going through repositories.
- Command records and query records differ: a command describes intent, a query record describes what the view needs.

When the split query is still too slow, or the screen needs values that are expensive to compute per request, maintain a separate read model (arch-read-model-projections).

## Bad Example

```python
def list_tickets(tickets: TicketRepository, status: Status | None) -> list[TicketListItem]:
    items = []
    for ticket in tickets.all(status=status):  # loads every message body and note
        items.append(
            TicketListItem(
                ticket_id=ticket.ticket_id,
                subject=ticket.subject,
                preview=make_preview(ticket.message),  # recomputed on every request
                has_note=bool((ticket.agent_note or "").strip()),
            )
        )
    return items
```

## Good Example

```python
@dataclass(frozen=True)
class TicketListItem:
    ticket_id: UUID
    subject: str
    status: Status
    updated_at: datetime


def ticket_list(session: Session, status: Status | None) -> list[TicketListItem]:
    stmt = select(
        TicketRow.ticket_id, TicketRow.subject, TicketRow.status, TicketRow.updated_at
    ).order_by(TicketRow.updated_at.desc())
    if status is not None:
        stmt = stmt.where(TicketRow.status == status)
    return [
        TicketListItem(row.ticket_id, row.subject, row.status, row.updated_at)
        for row in session.execute(stmt)
    ]
```

## Notes

- Business rules stay in command use cases ("a closed ticket cannot be reopened" raises a domain error that the interface maps once); queries decide nothing.
- A detail view of one record keeps reading the write model.
- Signals for a read model: list views need derived fields, a dashboard is slow, a screen filters on computed values, or reads and writes scale differently. Stay with plain use cases when read and write shapes match, the operations are CRUD and one view is enough.
- The cost of a read model: duplicated data, a projection to keep in step with every write, and stale reads if it is updated asynchronously.
- Event sourcing on the write side needs read models by construction (arch-event-sourcing).
