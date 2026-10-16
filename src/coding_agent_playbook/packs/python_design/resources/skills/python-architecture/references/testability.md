# Testability

Code is easy to test when everything a test must control arrives as an argument: data, the current time, new ids, randomness, and the collaborators that do I/O. Most tests then become a call with literal inputs and an assertion on a literal result.

## Fakes for the ports you own

- Write one in-memory fake per owned port, and make it behave like the real implementation: the same return types, the same domain errors (a missing id raises the domain not-found error, never `KeyError`), and the same ordering guarantees callers rely on.
- Name fakes after what they are: `InMemoryLoanRepository`, `RecordingSms`, `FakeLendingUnitOfWork`.
- Keep them in an importable module such as `tests/fakes.py` and import them explicitly. Fixtures may build them, but nothing imports from `conftest.py`.
- A fake that records what it was asked to do (`sent: list[tuple[str, str]]`) turns "was the mock called with" into an ordinary assertion on data.
- Keep `unittest.mock` for third-party objects you neither own nor can fake cheaply.
- Run one contract suite against both the fake and the real implementation so the two cannot drift apart; references/persistence.md has a template.

## Failure fakes

To drive an error path, subclass the fake and override the one method that should fail, raising the same specific error the real adapter raises:

```python
class RecordingSms:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def __call__(self, phone: str, message: str) -> None:
        self.sent.append((phone, message))


class UnreachableNumber(RecordingSms):
    """Fails for one number and delivers the rest."""

    def __init__(self, phone: str) -> None:
        super().__init__()
        self.phone = phone

    def __call__(self, phone: str, message: str) -> None:
        if phone == self.phone:
            raise SmsDeliveryError(phone)
        super().__call__(phone, message)
```

When a reminder job must keep going for the other members after one number fails, this fake lets a test assert both the delivered messages and the reported failure, with no network and no waiting.

## Time, ids and randomness

```python
Clock = Callable[[], datetime]
NewId = Callable[[], UUID]


def fixed_clock(moment: datetime) -> Clock:
    return lambda: moment


def sequential_ids() -> NewId:
    counter = itertools.count(1)
    return lambda: UUID(int=next(counter))
```

Production wiring passes `lambda: datetime.now(timezone.utc)` and `uuid4`. Code that needs randomness takes a `random.Random` instance, and tests pass one with a fixed seed. Freezing time with a library is for characterizing legacy code that cannot accept a clock yet, not a substitute for passing one.

## Making existing code testable

1. If nothing tests the code yet, pin its current behavior first with a characterization test at the outermost seam you can call, for example the CLI command run against a scratch database.
2. List every hidden input: objects built inside the function, module globals, the clock, `uuid4()`, environment variables, files read by path.
3. Lift each one to a parameter typed with the narrowest role the function uses, a `Callable` alias or a small Protocol, and move the concrete choice up into the composition root. Update every caller in the same change.
4. Rewrite the characterization test with fakes and literal inputs, then add the cases that were impossible before: time boundaries, failures and empty results.

## Which tests go where

| Test | Target | Collaborators |
|---|---|---|
| domain | rules and value objects | none: arguments in, values out |
| use case | application functions | fakes for every port, a fixed clock and id factory |
| contract | each repository or adapter | the real backend (an in-memory SQLite engine or a disposable server) and the fake, through one suite |
| edge | routes and CLI commands: parsing, status codes, wiring | `app.dependency_overrides` set in a fixture and cleared on teardown, or Click's `CliRunner` with a test `obj` |

Most tests belong in the first two rows. Edge tests cover only what the edge adds, such as a 404 for an unknown id or a 422 for a malformed body.

## Edge cases to check for each use case

- Empty input, a single item, the largest allowed amount.
- A missing record: the domain not-found error, with the id in its message.
- Duplicates: registering the same thing twice, and retrying the same command after a timeout.
- Invalid transitions: returning a tool that is not on loan, lending one that already is.
- Time boundaries: due exactly today, UTC midnight versus local midnight, month ends, leap days, daylight-saving changes for local-time rules.
- Partial failure: the second write fails and nothing is committed (`commits == 0` on the fake unit of work).
- Collaborator failure: the remote call raises its specific error, and the use case propagates or translates it as designed.
