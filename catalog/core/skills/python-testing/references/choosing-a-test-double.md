# Choosing a test double

Unit tests use fakes; persistence and endpoint tests use the real engine in a rolled-back transaction.
Take the first row that matches what the test must stand in for; the last column names the rule to open. This page only routes: the rules hold the examples and the reasons.

## Does the code own it?

Owned code runs for real. Never double the unit under test or its own helpers: only what the code does not own is replaced (pytest-test-doubles).

## Decision table

| The test stands in for | Double | Rule |
| --- | --- | --- |
| An owned port the code takes as a parameter (a store, a gateway Protocol) | A named fake (`Fake...`, in-memory state, no I/O) passed through the production parameter | pytest-test-doubles |
| One canned answer (a rate, a flag) | A stub-like fake: a named `Fake...` class or a plain function returning one fixed, realistic value through the same parameter | pytest-test-doubles |
| The clock, generated ids or randomness | A fixed clock, an id function or a seeded generator passed in | pytest-deterministic-tests; passing it in is python-coding's python-pure-core; array generators are ml-data's ml-seeded-randomness |
| Files | Real files under `tmp_path`, not a patched `open` | pytest-test-doubles |
| An environment variable, the working directory or a dict entry | The `monkeypatch` fixture | pytest-monkeypatch |
| A third-party SDK the code constructs itself | Patch the name where the code looks it up, with autospec | pytest-autospec |
| A module attribute in legacy code that cannot take a parameter yet | `monkeypatch.setattr` as the fallback, then add the parameter | pytest-monkeypatch; the refactor is python-architecture's arch-make-legacy-testable |
| SQL persistence code (a repository or adapter) | No double: the real engine in a rolled-back transaction | In web apps, web-application's sqlalchemy-test-rollback; elsewhere python-architecture's arch-contract-tests-for-fakes |
| An HTTP endpoint | The real app built per test; overrides only for out-of-process collaborators and the clock | In FastAPI repos, web-application's fastapi-dependency-overrides |

## Fake or stub?

A fake keeps state and answers later calls consistently, so the test asserts on what it holds after the Act. A stub-like fake returns one fixed answer. Both are named classes or functions, never a bare `Mock()` (pytest-test-doubles, pytest-autospec).

## Keeping a fake honest

- The fake raises the same errors as the real adapter, and failure fakes drive the error paths (python-architecture's arch-test-use-cases-with-fakes).
- One contract suite runs against both the fake and the real adapter (python-architecture's arch-contract-tests-for-fakes).

## Where the double lives

- Shared fakes live in an ordinary module such as `tests/fakes.py`, imported explicitly and never from `conftest.py` (pytest-conftest).
- Each test gets a fresh instance from a function-scoped fixture, never a shared module-level instance (pytest-fixtures, pytest-deterministic-tests).

## Signs the choice was wrong

The symptoms of a wrong double are the Mocking and Test isolation rows of reviewing-tests.md.
