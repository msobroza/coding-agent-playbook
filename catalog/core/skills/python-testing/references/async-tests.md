# Async tests

Use the async test plugin the repo already has; with none, use anyio's marker where FastAPI, Starlette or httpx is installed, and otherwise propose pytest-asyncio.
Take the first row that matches this repo; the pytest rule shows that row's code, and this page lists every row so the choice can be checked.

## Which marker, first match wins

| The repo has | Mark coroutine tests with | Async fixtures use | Rule |
| --- | --- | --- | --- |
| pytest-asyncio | `@pytest.mark.asyncio` on every coroutine test, explicit marks rather than `asyncio_mode = "auto"` | `@pytest_asyncio.fixture` (strict mode does not run an async `@pytest.fixture`) | pytest |
| FastAPI, Starlette or httpx, and no async plugin | `@pytest.mark.anyio` | A plain `@pytest.fixture`, plus one session-scoped `anyio_backend` fixture returning `"asyncio"` in the root `conftest.py` | pytest, pytest-conftest |
| Neither | Propose adding pytest-asyncio to the dev dependency group and wait for the user's agreement; until then drive the coroutine with `asyncio.run(...)` inside a sync test | None | pytest |

## Why this order

An installed plugin wins. The repo already configured it (its mode, its loop scope), and the pytest-conventions-feedback hook checks its marks.

FastAPI, Starlette and httpx install AnyIO, whose test plugin registers itself, so the anyio marker needs no new dependency. Starlette is in the list for that reason: a Starlette app without FastAPI has AnyIO too.

A new dependency is the user's call and is never added silently, so the last row proposes it and falls back to `asyncio.run(...)`.

One suite, one marker: never mix asyncio and anyio marks on tests that share async fixtures.

## Async fixtures and loop scope

- Tear down after `yield`, at the narrowest scope that works (pytest-fixtures).
- A session-scoped async resource, such as a database engine, needs the session-scoped `anyio_backend` fixture (anyio), or `loop_scope="session"` on both the fixture and the test mark (pytest-asyncio).
- In web apps with SQLAlchemy that engine and the per-test rolled-back session are web-application's sqlalchemy-test-rollback; follow its fixture.

## What the async test awaits

- A typed async fake passed through the production parameter (pytest-test-doubles); the FakeRates example in the pytest rule shows the one-method shape.
- A full async fake of an owned port (python-architecture's arch-test-use-cases-with-fakes).
- An endpoint through `httpx.AsyncClient` with `ASGITransport`, in FastAPI repos (web-application's fastapi-dependency-overrides).

## Findings and configuration

- A pytest-asyncio-mark finding from the feedback hook means a coroutine test lacks `@pytest.mark.asyncio` (pytest).
- The test runner's settings block and marker registration: python-tooling's pytest-configuration.
- The coroutine under test, its concurrent awaits and its deadlines: python-coding's python-async.

Related guides: choosing-a-test-double.md, reviewing-tests.md.
