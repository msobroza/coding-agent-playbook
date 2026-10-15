# Worked example: a tool-lending API

A community tool library lends drills, ladders and hedge trimmers to its members. This small FastAPI service edits a tool's details and lends a tool out. It sits at step 3 of the persistence flow because lending checks one repository, writes another, and must commit once. A service without such an operation would stop at step 1, with an injected session and no ports.

Every module sits in a directory the default layer map recognizes, so the layer checker should report no violations for this tree.

```text
tool_library/
  domain/model.py       domain: typed records, the loan rule, the error hierarchy
  services/lending.py   application: the ports it consumes and the use cases
  db/sql.py             infrastructure: mapped tables, repositories, unit of work
  api/routes.py         interface: request and response models, the router
  deps.py               composition root: per-request providers
  main.py               composition root: settings, lifespan, error mapping, app
tests/
  fakes.py  test_lending.py
```

## Domain

```python
# tool_library/domain/model.py
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final
from uuid import UUID

LOAN_PERIOD: Final = timedelta(days=14)


@dataclass(frozen=True)
class Tool:
    tool_id: UUID
    name: str
    notes: str | None = None


@dataclass(frozen=True)
class Loan:
    loan_id: UUID
    tool_id: UUID
    member_id: UUID
    due_on: date
    returned_on: date | None = None


def open_loan(tool: Tool, loan_id: UUID, member_id: UUID, today: date) -> Loan:
    return Loan(loan_id, tool.tool_id, member_id, due_on=today + LOAN_PERIOD)


class LibraryError(Exception):
    """Root of the tool library's own failures."""


class NotFoundError(LibraryError):
    """A record the caller asked for does not exist."""


class ToolNotFoundError(NotFoundError):
    def __init__(self, tool_id: UUID) -> None:
        super().__init__(f"no tool with id {tool_id}")
        self.tool_id = tool_id


class ToolOnLoanError(LibraryError):
    def __init__(self, tool_id: UUID) -> None:
        super().__init__(f"tool {tool_id} is already on loan")
        self.tool_id = tool_id
```

## Application

The ports live beside the use cases that consume them. The SQL classes satisfy them structurally and never import this module.

```python
# tool_library/services/lending.py
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from enum import Enum
from typing import Final, Protocol
from uuid import UUID

from tool_library.domain.model import Loan, Tool, ToolOnLoanError, open_loan


class ToolRepository(Protocol):
    def get(self, tool_id: UUID) -> Tool: ...  # raises ToolNotFoundError
    def save(self, tool: Tool) -> None: ...


class LoanRepository(Protocol):
    def open_loan_for(self, tool_id: UUID) -> Loan | None: ...
    def add(self, loan: Loan) -> None: ...


class LendingUnitOfWork(Protocol):
    @property
    def tools(self) -> ToolRepository: ...
    @property
    def loans(self) -> LoanRepository: ...
    def commit(self) -> None: ...


class Unset(Enum):
    TOKEN = 0


UNSET: Final = Unset.TOKEN


@dataclass(frozen=True)
class ToolChanges:
    """A partial update: UNSET keeps the current value, None clears `notes`."""

    name: str | Unset = UNSET
    notes: str | None | Unset = UNSET


def update_tool(uow: LendingUnitOfWork, tool_id: UUID, changes: ToolChanges) -> Tool:
    tool = uow.tools.get(tool_id)
    updated = replace(
        tool,
        name=tool.name if changes.name is UNSET else changes.name,
        notes=tool.notes if changes.notes is UNSET else changes.notes,
    )
    uow.tools.save(updated)
    uow.commit()
    return updated


def borrow_tool(
    uow: LendingUnitOfWork, tool_id: UUID, member_id: UUID, today: date, new_id: Callable[[], UUID]
) -> Loan:
    tool = uow.tools.get(tool_id)
    if uow.loans.open_loan_for(tool_id) is not None:
        raise ToolOnLoanError(tool_id)
    loan = open_loan(tool, new_id(), member_id, today)
    uow.loans.add(loan)
    uow.commit()
    return loan
```

## Infrastructure

```python
# tool_library/db/sql.py
from dataclasses import asdict
from datetime import date
from uuid import UUID

from sqlalchemy import ForeignKey, Index, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from tool_library.domain.model import Loan, Tool, ToolNotFoundError, ToolOnLoanError


class Base(DeclarativeBase):
    pass


class ToolRow(Base):
    __tablename__ = "tools"
    tool_id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str]
    notes: Mapped[str | None]


class LoanRow(Base):
    __tablename__ = "loans"
    __table_args__ = (  # at most one open loan per tool, enforced by the database
        Index(
            "one_open_loan_per_tool",
            "tool_id",
            unique=True,
            sqlite_where=text("returned_on IS NULL"),
            postgresql_where=text("returned_on IS NULL"),
        ),
    )
    loan_id: Mapped[UUID] = mapped_column(primary_key=True)
    tool_id: Mapped[UUID] = mapped_column(ForeignKey("tools.tool_id"), index=True)
    member_id: Mapped[UUID]
    due_on: Mapped[date]
    returned_on: Mapped[date | None]


class SqlToolRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, tool_id: UUID) -> Tool:
        row = self._row(tool_id)
        return Tool(row.tool_id, row.name, row.notes)

    def save(self, tool: Tool) -> None:
        row = self._row(tool.tool_id)
        row.name, row.notes = tool.name, tool.notes
        self._session.flush()

    def _row(self, tool_id: UUID) -> ToolRow:
        row = self._session.get(ToolRow, tool_id)
        if row is None:
            raise ToolNotFoundError(tool_id)
        return row


class SqlLoanRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def open_loan_for(self, tool_id: UUID) -> Loan | None:
        stmt = select(LoanRow).where(LoanRow.tool_id == tool_id, LoanRow.returned_on.is_(None))
        row = self._session.scalars(stmt).one_or_none()
        if row is None:
            return None
        return Loan(row.loan_id, row.tool_id, row.member_id, row.due_on, row.returned_on)

    def add(self, loan: Loan) -> None:
        self._session.add(LoanRow(**asdict(loan)))
        try:
            self._session.flush()
        except IntegrityError as exc:  # a fresh loan can only break one_open_loan_per_tool
            raise ToolOnLoanError(loan.tool_id) from exc


class SqlLendingUnitOfWork:
    """Both repositories share the request's session, so one commit covers both."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self.tools = SqlToolRepository(session)
        self.loans = SqlLoanRepository(session)

    def commit(self) -> None:
        self._session.commit()
```

The check in `borrow_tool` runs in one transaction, yet two simultaneous requests can both see a free tool. The partial unique index `one_open_loan_per_tool` closes that race in the database, and `SqlLoanRepository.add` translates the losing request's `IntegrityError` into `ToolOnLoanError`, so that request gets the same 409 as one refused by the check instead of a 500.

## Interface

```python
# tool_library/api/routes.py
from datetime import date
from uuid import UUID, uuid4

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, field_validator

from tool_library.deps import Lending, Today
from tool_library.services import lending

NOT_FOUND = {"description": "No tool has this id"}
ON_LOAN = {"description": "The tool is already on loan"}


class ToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tool_id: UUID
    name: str
    notes: str | None


class ToolPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def name_cannot_be_cleared(cls, value: str | None) -> str:
        if value is None:  # validators skip defaults, so this null was sent explicitly
            raise ValueError("name cannot be null")
        return value


class LoanIn(BaseModel):
    member_id: UUID


class LoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    loan_id: UUID
    due_on: date


router = APIRouter(prefix="/tools", tags=["tools"])


@router.patch("/{tool_id}", responses={404: NOT_FOUND})
def patch_tool(tool_id: UUID, body: ToolPatch, uow: Lending) -> ToolOut:
    changes = lending.ToolChanges(**body.model_dump(exclude_unset=True))
    return ToolOut.model_validate(lending.update_tool(uow, tool_id, changes))


@router.post("/{tool_id}/loans", status_code=201, responses={404: NOT_FOUND, 409: ON_LOAN})
def borrow_tool(tool_id: UUID, body: LoanIn, uow: Lending, today: Today) -> LoanOut:
    loan = lending.borrow_tool(uow, tool_id, body.member_id, today, uuid4)
    return LoanOut.model_validate(loan)
```

Routes are plain `def` because the session is synchronous, so FastAPI runs them in its threadpool.

## Composition root

```python
# tool_library/deps.py
from collections.abc import Iterator
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from tool_library.db.sql import SqlLendingUnitOfWork
from tool_library.services.lending import LendingUnitOfWork


def get_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:  # closed on every path; uncommitted work is dropped
        yield session


def get_uow(session: Annotated[Session, Depends(get_session)]) -> LendingUnitOfWork:
    return SqlLendingUnitOfWork(session)


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


Lending = Annotated[LendingUnitOfWork, Depends(get_uow)]
Today = Annotated[date, Depends(today_utc)]
```

```python
# tool_library/main.py
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tool_library.api import routes
from tool_library.domain.model import LibraryError, NotFoundError, ToolOnLoanError

HTTP_STATUS: Final[dict[type[LibraryError], int]] = {NotFoundError: 404, ToolOnLoanError: 409}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TOOL_LIBRARY_")
    database_url: str  # no default: startup fails when it is missing


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = create_engine(Settings().database_url)
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    try:
        yield
    finally:
        engine.dispose()


async def library_error_response(request: Request, exc: Exception) -> JSONResponse:
    mapped = [cls for cls in HTTP_STATUS if isinstance(exc, cls)]
    if not mapped:
        raise exc  # unmapped: the default handler logs it and answers a plain 500
    closest = min(mapped, key=type(exc).__mro__.index)
    return JSONResponse(status_code=HTTP_STATUS[closest], content={"detail": str(exc)})


def create_app() -> FastAPI:
    app = FastAPI(title="Tool library", lifespan=lifespan)
    app.add_exception_handler(LibraryError, library_error_response)
    app.include_router(routes.router)
    return app


app = create_app()
```

## Tests

```python
# tests/fakes.py
from uuid import UUID

from tool_library.domain.model import Loan, Tool, ToolNotFoundError, ToolOnLoanError


class InMemoryToolRepository:
    def __init__(self, *tools: Tool) -> None:
        self.by_id = {tool.tool_id: tool for tool in tools}

    def get(self, tool_id: UUID) -> Tool:
        if tool_id not in self.by_id:
            raise ToolNotFoundError(tool_id)  # the same contract as the SQL repository
        return self.by_id[tool_id]

    def save(self, tool: Tool) -> None:
        self.get(tool.tool_id)  # an unknown id fails here exactly as it does in SQL
        self.by_id[tool.tool_id] = tool


class InMemoryLoanRepository:
    def __init__(self) -> None:
        self.loans: list[Loan] = []

    def open_loan_for(self, tool_id: UUID) -> Loan | None:
        open_loans = (loan for loan in self.loans if loan.returned_on is None)
        return next((loan for loan in open_loans if loan.tool_id == tool_id), None)

    def add(self, loan: Loan) -> None:
        if self.open_loan_for(loan.tool_id) is not None:
            raise ToolOnLoanError(loan.tool_id)  # the SQL index refuses it the same way
        self.loans.append(loan)


class FakeLendingUnitOfWork:
    def __init__(self, *tools: Tool) -> None:
        self.tools = InMemoryToolRepository(*tools)
        self.loans = InMemoryLoanRepository()
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1
```

```python
# tests/test_lending.py
from collections.abc import Iterator
from datetime import date
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from tests.fakes import FakeLendingUnitOfWork, InMemoryLoanRepository
from tool_library.deps import get_uow, today_utc
from tool_library.domain.model import LibraryError, Loan, Tool, ToolOnLoanError
from tool_library.main import create_app
from tool_library.services.lending import borrow_tool

LADDER = Tool(UUID(int=2), "step ladder", notes="left foot wobbles")
MONDAY = date(2026, 3, 2)


class LedgerOutOfSyncError(LibraryError):
    """A domain error deliberately missing from HTTP_STATUS."""


class OutOfSyncLoans(InMemoryLoanRepository):
    def open_loan_for(self, tool_id: UUID) -> Loan | None:
        raise LedgerOutOfSyncError(f"loan ledger disagrees about {tool_id}")


@pytest.fixture
def uow() -> FakeLendingUnitOfWork:
    return FakeLendingUnitOfWork(LADDER)


@pytest.fixture
def client(uow: FakeLendingUnitOfWork) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_uow] = lambda: uow
    app.dependency_overrides[today_utc] = lambda: MONDAY
    # Not entered with `with`, so the lifespan never runs: no settings, no database.
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def test_a_lent_tool_cannot_be_borrowed_again(uow: FakeLendingUnitOfWork) -> None:
    first = borrow_tool(uow, LADDER.tool_id, UUID(int=50), MONDAY, lambda: UUID(int=900))
    with pytest.raises(ToolOnLoanError):
        borrow_tool(uow, LADDER.tool_id, UUID(int=51), MONDAY, lambda: UUID(int=901))
    assert first.due_on == date(2026, 3, 16)
    assert uow.commits == 1  # the refused loan committed nothing


def test_unknown_tool_is_404(client: TestClient) -> None:
    missing = UUID(int=404)
    response = client.patch(f"/tools/{missing}", json={"name": "bench vise"})
    assert response.status_code == 404
    assert response.json() == {"detail": f"no tool with id {missing}"}


def test_patch_with_null_notes_clears_them_and_keeps_the_name(client: TestClient) -> None:
    response = client.patch(f"/tools/{LADDER.tool_id}", json={"notes": None})
    assert response.status_code == 200
    assert response.json() == {"tool_id": str(LADDER.tool_id), "name": "step ladder", "notes": None}


def test_unmapped_domain_error_is_500(client: TestClient, uow: FakeLendingUnitOfWork) -> None:
    uow.loans = OutOfSyncLoans()
    response = client.post(f"/tools/{LADDER.tool_id}/loans", json={"member_id": str(UUID(int=7))})
    assert response.status_code == 500
```

## What each choice shows

- Typed records cross every boundary. The only `dict` on the request path is `model_dump(exclude_unset=True)`, unpacked into `ToolChanges` in the route that produced it.
- `exclude_unset`, not `exclude_none`, is what lets a PATCH tell "leave `notes` alone" (key absent) from "clear `notes`" (explicit null). A field that may not be cleared rejects an explicit null in its schema.
- `get_session` closes the session on every path, and use cases commit explicitly, so nothing depends on when provider teardown runs. The lifespan reads settings once, builds the engine and disposes of it on shutdown; nothing connects at import time.
- Domain errors are mapped in one table. A `LibraryError` subclass missing from it is re-raised and answered as a 500, and no HTTP type appears below the routes.
- Driver errors stop at the repository. The open-loan index's `IntegrityError` leaves `SqlLoanRepository.add` as `ToolOnLoanError`, and the in-memory fake raises the same error, so a lost race and an ordinary refusal both answer 409.
- The use-case test needs only fakes. The API tests override two providers on a fresh app and cover only what the edge adds: status codes and the error body.
