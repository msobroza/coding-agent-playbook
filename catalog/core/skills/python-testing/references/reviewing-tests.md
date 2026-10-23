# Reviewing tests

Find the lint code, the hook finding or the review symptom below and open the rule in its last column. A rule marked "when the repo depends on X" is in this repo's index only then.
The PT codes and the hook's findings all report under the pytest rule, while their topics live in the split rules this page names.

## Lint codes, ruff PT

| Code | What it flags | Rule |
| --- | --- | --- |
| PT006, PT007 | Parametrize names or values of the wrong type | pytest-parametrize |
| PT009 | A unittest-style `assertEqual` | pytest (plain functions), pytest-assertions |
| PT011 | A `pytest.raises` too broad, without `match=` | pytest-assertions |
| PT018 | A composite `assert a and b` | pytest-assertions |
| PT027 | A unittest-style `assertRaises` | pytest-arrange-act-assert (`pytest.raises` around the Act only) |

## Hook findings, pytest-conventions-feedback

| Finding | Rule |
| --- | --- |
| pytest-loop-assert | pytest-parametrize, pytest-no-test-logic |
| pytest-unittest-class | pytest; the Hypothesis state machine's `TestCase` entry point is the one exception (pytest-hypothesis-stateful) |
| pytest-asyncio-mark | pytest, and async-tests.md for every marker branch |

## Review symptoms

### Mocking

| Symptom | Rule |
| --- | --- |
| The code's own helpers doubled; many doubles in one test; asserts on call order; a freeze-time library outside legacy characterization | pytest-test-doubles |
| A bare `Mock()` or `MagicMock()`; a patch at the defining module instead of where the name is looked up | pytest-autospec |
| A mocked database session, or in-memory SQLite standing in for another production database | web-application's sqlalchemy-test-rollback (web apps); python-architecture's arch-contract-tests-for-fakes (elsewhere) |

### Test structure

| Symptom | Rule |
| --- | --- |
| A name that says what is called, not what happens; a `skip` or `xfail` added to turn the suite green | pytest |
| Setup and checks interleaved; two Acts in one test | pytest-arrange-act-assert |
| One test walking a whole lifecycle | pytest-one-behavior |
| `if`, `for` or `try` in a test body; an expectation recomputed with the production formula | pytest-no-test-logic |
| `is not None` or `len(...) > 0` as the only check; a float compared with `==` | pytest-assertions |

### Test isolation

| Symptom | Rule |
| --- | --- |
| Passes alone and fails in the suite; unseeded randomness; `now()`; the network | pytest-deterministic-tests |
| `os.environ` assigned; a hand-written set-then-restore; a module global reassigned | pytest-monkeypatch |

### Fixtures

| Symptom | Rule |
| --- | --- |
| A session-scoped mutable object; `yield` plus `addfinalizer`; an untyped fixture | pytest-fixtures |
| An import from `conftest.py`; an oversized root `conftest.py` | pytest-conftest |
| `user`, `admin_user` and `inactive_user` fixtures side by side | pytest-factory-fixtures |

### Parametrization

| Symptom | Rule |
| --- | --- |
| Copy-pasted tests that differ only in data | pytest-parametrize |
| Opaque case ids such as `payload0` | pytest-parametrize-ids |

### Coverage

| Symptom | Rule |
| --- | --- |
| Only the happy path tested | pytest-edge-cases |
| A coverage percentage cited as proof of quality | pytest-branch-coverage, when the repo depends on pytest-cov or coverage |
| An invariant checked on one hand-picked input | pytest-hypothesis-properties, when the repo depends on hypothesis |
| A bug that needs a sequence of calls to show | pytest-hypothesis-stateful, when the repo depends on hypothesis |

## Outside this skill

- Test-runner settings, markers, warning filters and the coverage threshold: python-tooling's pytest-configuration.
- The layer a test belongs at: python-architecture's arch-tests-by-layer.
- Endpoint and database tests: web-application's fastapi-dependency-overrides and sqlalchemy-test-rollback.
- Numeric arrays and frames: ml-data's ml-numeric-assertions.

Related guides: choosing-a-test-double.md, async-tests.md.
