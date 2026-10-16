# CQRS and event sourcing

Both answer specific problems: slow or awkward reads for CQRS, history as a requirement for event sourcing. Neither is a starting point. SKILL.md lists the signals that justify each; this file covers how to build them without the usual mistakes.

## CQRS in two sizes

**Split in code first.** Commands are use cases that change state and return little beyond an id. Queries return read records shaped for one screen, selecting only the columns that screen shows, straight from SQL, without loading aggregates or going through repositories. This costs almost nothing and fixes most slow list endpoints.

```python
@dataclass(frozen=True)
class ShelfEntry:
    tool_id: UUID
    name: str
    due_on: date | None  # None while the tool is on the shelf


def shelf_board(session: Session) -> list[ShelfEntry]:
    open_loans = (
        select(LoanRow.tool_id, LoanRow.due_on).where(LoanRow.returned_on.is_(None)).subquery()
    )
    stmt = (
        select(ToolRow.tool_id, ToolRow.name, open_loans.c.due_on)
        .outerjoin(open_loans, open_loans.c.tool_id == ToolRow.tool_id)
        .order_by(ToolRow.name)
    )
    return [ShelfEntry(row.tool_id, row.name, row.due_on) for row in session.execute(stmt)]
```

**A separate read model.** When the split query is still too slow, or the screen needs values that are expensive to compute per request (loan counts across years, a text preview, a score), maintain a projection table:

- A projector turns write-side state, or an event, into one read row and upserts it. Keep the computation a pure function so it is tested without a database.
- Run the projector in the same transaction as the write, so readers never see a write without its projection. Run it asynchronously, from an outbox or the event log, only when write latency matters more than freshness, and then let the screen show how fresh its data is.
- Never project values that depend on the current time, such as "overdue" or "days left". Store the inputs (`due_on`) and compare at query time; otherwise the read model is wrong by tomorrow.
- Ship a rebuild command that recomputes every read row from the source of truth. The first change to the read shape will need it.
- A detail view of one record can keep reading the write model.

```python
@dataclass(frozen=True)
class ToolPopularity:
    tool_id: UUID
    times_lent: int
    last_lent_on: date | None


def project_popularity(tool_id: UUID, lent_on: Sequence[date]) -> ToolPopularity:
    return ToolPopularity(tool_id, len(lent_on), max(lent_on, default=None))
```

## Event sourcing

The source of truth becomes an append-only log of events, one stream per aggregate (here, one per tool). Current state is a fold over the stream.

**Events.**

- Use frozen dataclasses named in the past tense for something that happened (`ToolLent`, `ToolReturned`), not imperatives (`LendTool`, which is a command).
- Carry ids and plain values, never ORM objects.
- Give every event an `occurred_at` that is timezone-aware UTC and supplied by the caller's clock. A `default_factory=datetime.now` field is both naive local time and a hidden clock.
- Version the payload. When the shape changes, add an upcaster that converts old payloads into the current class when they are read. Never rewrite stored events.

```python
@dataclass(frozen=True)
class ToolLent:
    tool_id: UUID
    member_id: UUID
    due_on: date
    occurred_at: datetime
    schema_version: int = 1


@dataclass(frozen=True)
class ToolReturned:
    tool_id: UUID
    occurred_at: datetime
    schema_version: int = 1


ToolEvent = ToolLent | ToolReturned
```

**State and decisions are pure functions.** `apply` folds one event into the state; a decision function checks the rules against the state and returns new events or raises a domain error.

```python
@dataclass(frozen=True)
class ToolState:
    on_loan_to: UUID | None = None


def apply(state: ToolState, event: ToolEvent) -> ToolState:
    if isinstance(event, ToolLent):
        return replace(state, on_loan_to=event.member_id)
    return replace(state, on_loan_to=None)


def lend(state: ToolState, tool_id: UUID, member_id: UUID, due_on: date, now: datetime) -> ToolLent:
    if state.on_loan_to is not None:
        raise ToolOnLoanError(tool_id)
    return ToolLent(tool_id, member_id, due_on, occurred_at=now)
```

**The store.** Appends only. Each event gets a sequence number within its stream, and every append states the version its decision was based on. When the stream has moved on, the store rejects the append with a concurrency error, and the caller reloads and decides again. In SQL, a unique constraint on (stream id, version) enforces this.

```python
class ToolEventStore(Protocol):
    def load(self, tool_id: UUID) -> tuple[list[ToolEvent], int]: ...  # events, version
    def append(self, tool_id: UUID, events: Sequence[ToolEvent], expected_version: int) -> None: ...


def lend_tool(
    store: ToolEventStore, tool_id: UUID, member_id: UUID, due_on: date, clock: Clock
) -> None:
    history, version = store.load(tool_id)
    state = reduce(apply, history, ToolState())
    event = lend(state, tool_id, member_id, due_on, clock())
    store.append(tool_id, [event], expected_version=version)
```

**Projections.** Pure functions over events that feed read tables. Update them in the write path, in the same transaction as the append, or from a subscriber that reads the log in order and records the last position it processed. Either way, a projection can be rebuilt by replaying from the start.

**Snapshots.** Add them only when replay time is measured to be a problem. Store the stream id, version and state every N events, then load the newest snapshot and replay only the events after it. A snapshot is a cache: the events remain the truth, and a snapshot written with an older state shape is discarded, not migrated.

**Caching state.** Do not put `functools.cache` or `lru_cache` on methods that replay events. The cache keys on `self`, keeps every instance alive, and keeps serving the old state after the next append. Keep an explicit cached state that the append path updates, or read from a projection.

**Costs to accept before starting.**

- Personal data inside events is hard to erase. Keep it out of events and store a reference, or encrypt it per person and delete the key on request.
- Every consumer of the log must handle every past event version, forever.
- Reporting needs a projection for each question; ad hoc SQL over the raw log is painful.
- When the real requirement is "who changed what, and when", an audit table written in the same transaction as ordinary rows delivers it at a fraction of the cost.
