# Persistence

Detail for steps 1 to 3 of the persistence flow in SKILL.md: session lifetime, the session as the data-access layer, typed repositories, the unit of work, and contract tests. Examples use SQLAlchemy 2.0 and a tool-lending domain; worked-example.md wires a slimmer version of the same pieces into a FastAPI app.

## Session lifetime

- Use one session per request, job run or command, created from a `sessionmaker` that the composition root built from the engine. Never share a module-level session across requests or threads.
- Hand the session out from a context manager so it closes on every path. In FastAPI that is a `yield` provider:

```python
def get_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:  # close() also discards uncommitted work
        yield session
```

- Commit in the use case, or in the unit of work it uses, not in the provider's teardown. The point at which `yield` dependencies tear down, relative to sending the response, has changed between FastAPI versions, so a commit there can fail after the client has already received a success.
- Convert rows to records while the session is open. A lazy relationship touched after `close()` raises `DetachedInstanceError`. `expire_on_commit=False` on the factory keeps already loaded attributes readable after a commit.
- With `AsyncSession` and `async_sessionmaker`, never share one session between concurrently running tasks.
- Migrations (Alembic) own the production schema. `Base.metadata.create_all` belongs in tests and throwaway local setups.

## Step 1: the session as the data-access layer

```python
def tools_in_category(session: Session, category: Category) -> list[ToolSummary]:
    stmt = select(ToolRow.tool_id, ToolRow.name).where(ToolRow.category == category)
    rows = session.execute(stmt.order_by(ToolRow.name))
    return [ToolSummary(tool_id=row.tool_id, name=row.name) for row in rows]
```

The use case selects only the columns it returns and hands back typed records, never ORM rows. It receives the session and never creates the engine or the session itself. This is the whole persistence design for many services.

## Step 2: typed repositories

- Declare one Protocol per aggregate, beside the use cases that consume it, named after the entity (`ToolRepository`) and listing only the methods they call.
- Take and return typed records. Name parameters `tool_id` rather than `id`, which shadows the builtin.
- When a row is missing, raise the domain not-found error carrying the id, in every implementation. Return `T | None` only from queries where absence is a normal answer, and let the name say so (`open_loan_for`).
- Add and flush, never commit: the use case owns the transaction. Flushing inside the repository surfaces constraint violations where they can be translated.
- Name query methods after the question they answer (`due_before(day)`) and load relationships eagerly inside them, with `selectinload` for collections and `joinedload` for a single parent, instead of filtering a full listing in Python or triggering one lazy load per row.
- Translate driver errors at this boundary, raising the domain error `from` the original. When a table has several unique constraints, inspect the constraint name before choosing the domain error.

```python
class SqlToolRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, tool_id: UUID) -> Tool:
        row = self._session.get(ToolRow, tool_id)
        if row is None:
            raise ToolNotFoundError(tool_id)
        return row.to_record()

    def add(self, tool: Tool) -> None:
        self._session.add(ToolRow.from_record(tool))
        try:
            self._session.flush()
        except IntegrityError as exc:  # the only unique constraint on tools is the barcode
            raise DuplicateBarcodeError(tool.barcode) from exc
```

## Step 3: the unit of work

The use case sees one object that hands out repositories sharing a single transaction and exposes one `commit()`:

```python
class LendingUnitOfWork(Protocol):
    @property
    def tools(self) -> ToolRepository: ...
    @property
    def loans(self) -> LoanRepository: ...
    def commit(self) -> None: ...
```

In a FastAPI app the request's session provider already owns the session's lifetime, so the SQL implementation only wraps that session (worked-example.md shows it). In a worker or CLI, the unit of work can own the session itself as a context manager:

```python
class SqlLendingUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __enter__(self) -> Self:
        self._session = self._session_factory()
        self.tools = SqlToolRepository(self._session)
        self.loans = SqlLoanRepository(self._session)
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._session.rollback()  # a no-op after commit(); undoes everything otherwise
        self._session.close()

    def commit(self) -> None:
        self._session.commit()
```

Rules that keep it honest:

- Commit exactly once per use case, at the end. Never commit inside a loop over items and never inside a repository.
- On failure, do nothing special: the exception propagates and the exit path rolls back. Do not catch it inside the use case to log and continue.
- Perform check-then-act (is the tool free? then lend it) inside one unit of work, and back the check with a database constraint, such as a partial unique index on open loans per tool. Two concurrent requests can both pass a check made in Python.
- Effects that leave the process, such as emails or messages to a broker, run after the commit, or go into an outbox table written in the same transaction and delivered by a worker. Never send first and commit second.

## Contract tests

One suite, parametrized over the fake and the real implementation, keeps the fake trustworthy:

```python
@pytest.fixture(params=["memory", "sql"])
def tools(request: pytest.FixtureRequest) -> Iterator[ToolRepository]:
    if request.param == "memory":
        yield InMemoryToolRepository()
        return
    engine = create_engine(URL.create("sqlite"))  # in-memory database, nothing on disk
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield SqlToolRepository(session)
    engine.dispose()


def test_unknown_tool_raises_not_found(tools: ToolRepository) -> None:
    missing = UUID(int=404)
    with pytest.raises(ToolNotFoundError) as caught:
        tools.get(missing)
    assert caught.value.tool_id == missing


def test_added_tool_reads_back_unchanged(tools: ToolRepository) -> None:
    sander = Tool(UUID(int=1), "orbital sander", Category.POWER, barcode="TL-0042")
    tools.add(sander)
    assert tools.get(sander.tool_id) == sander
```

Every behavior a use case relies on gets a contract test: not-found errors, duplicate handling, ordering, and what a query returns for an empty table. When the production database has features SQLite lacks, such as partial indexes with particular semantics or native enum types, run the SQL half of the suite against a disposable instance of the real engine.
