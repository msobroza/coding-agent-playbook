---
id: python-testing
name: python-testing
description: "Guides how tests in this repo's pytest suite are written and reviewed."
playbook:
  use_when: "writing, changing or reviewing tests, fixtures or conftest.py"
  files: "Test files and conftest.py"
  sections:
    - id: mocking
      title: "Mocking"
      impact: CRITICAL
      summary: "Double only what the code does not own, and keep every double faithful to the real interface."
      open_when: "A test stands in for a collaborator with a fake class, a stub, Mock, create_autospec, mock.patch or mocker."
    - id: structure
      title: "Test Structure"
      impact: HIGH
      summary: "Lay out, name and shape each test so a failure points at one behavior and an assertion that could fail."
      open_when: "A test function is added or reworked: its name, asserts, pytest.raises, if/for/try in the body, or async or skip marks."
    - id: isolation
      title: "Test Isolation"
      impact: HIGH
      summary: "Keep every test independent of run order, the environment, the clock and randomness."
      open_when: "A test touches os.environ, the clock, random numbers, the network or module state, or fails only in some run orders."
    - id: fixtures
      title: "Fixtures"
      impact: HIGH
      summary: "Share setup without hiding it: narrow scope, nearest conftest.py, factories for variations."
      open_when: "A @pytest.fixture or conftest.py is added or changed, or several tests build the same objects in their Arrange step."
    - id: parametrization
      title: "Parametrization"
      impact: MEDIUM
      summary: "Collapse duplicated tests into case tables that run and report each case on its own."
      open_when: "Two tests differ only in inputs and expected values, or a parametrize decorator, ids= or pytest.param is edited."
    - id: coverage
      title: "Coverage"
      impact: MEDIUM
      summary: "Find the inputs and paths the suite still misses: edge-case checklists, branch coverage and property-based tests."
      open_when: "Deciding which cases to add: boundary and error inputs, a coverage report's misses, a regression test, or Hypothesis."
  references:
    - path: references/choosing-a-test-double.md
      open_when: "Before picking what replaces a dependency in a test: fake, stub, autospec, monkeypatch, override or a real database."
      applies_if:
        has_framework: ["pytest"]
    - path: references/async-tests.md
      open_when: "Adding the first async test or async fixture, or choosing between pytest-asyncio, anyio's marker and asyncio.run."
      applies_if:
        has_framework: ["pytest"]
    - path: references/reviewing-tests.md
      open_when: "Reviewing a test diff, or a ruff PT code or pytest-conventions-feedback finding that links to the pytest rule."
      applies_if:
        has_framework: ["pytest"]
---

# Python testing

Test-writing practices for readable, maintainable and trustworthy tests in this repo: layout, naming, parametrized cases, test doubles, fixtures, test data and isolation. Production code changed alongside a test still follows the python-coding skill.

## Quick Reference

### Structure

```python
def test_expired_token_is_rejected() -> None:
    # Arrange
    token = make_token(expires_at=YESTERDAY)

    # Act
    result = validate(token)

    # Assert
    assert result.valid is False
```

### Fixtures

```python
@pytest.fixture  # function scope by default: a fresh value per test
def user() -> User:
    return User(name="alice", email="alice@example.com")


@pytest.fixture  # a factory when tests need variations of one object
def make_user() -> Callable[..., User]:
    def _make(*, name: str = "alice", active: bool = True) -> User:
        return User(name=name, email=f"{name}@example.com", active=active)

    return _make
```

### Parametrize

```python
@pytest.mark.parametrize(
    ("email", "valid"),
    [
        pytest.param("a@example.com", True, id="simple-address"),
        pytest.param("a@sub.example.com", True, id="subdomain"),
        pytest.param("no-at-sign", False, id="missing-at"),
        pytest.param("", False, id="empty-string"),
    ],
)
def test_email_validation(email: str, valid: bool) -> None:
    assert is_valid_email(email) is valid
```

### Mocking

```python
# A named fake passed through the production parameter; assert on what it holds.
class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[Email] = []

    def send(self, email: Email) -> None:
        self.sent.append(email)


def test_signup_sends_a_welcome_email() -> None:
    mailer = FakeMailer()

    signup(email="alice@example.com", mailer=mailer)

    assert mailer.sent == [Email(to="alice@example.com", template="welcome")]


# Fallback for a third-party seam the code cannot take as a parameter yet:
# patch the name where the code looks it up, with autospec.
def test_signup_reports_to_the_analytics_sdk() -> None:
    with patch("app.signup.analytics.track", autospec=True) as track:
        signup(email="alice@example.com", mailer=FakeMailer())

    track.assert_called_once_with("signup", plan="free")


# The monkeypatch fixture for environment variables; it undoes the change.
def test_reads_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "test-key")

    config = load_config()

    assert config.api_key == "test-key"
```

## See Also

- python-tooling: the test runner's configuration, markers and the coverage threshold.
- python-coding: the production code under test.
- python-architecture: testing across layer seams and fakes of owned ports.
- web-application: dependency overrides and database tests in a rolled-back transaction.
- ml-data: numeric, array and frame assertions.
