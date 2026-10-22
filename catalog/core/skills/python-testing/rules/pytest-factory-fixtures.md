---
id: pytest-factory-fixtures
name: Factory fixtures
description: "When tests need variations of one object, return a factory with keyword-only parameters and valid defaults from the fixture, and clean up what it created after yield."
version: 1
scope: scoped
globs:
  - "tests/**/*.py"
  - "**/conftest.py"
applies_if:
  has_framework: ["pytest"]
section: fixtures
priority: 50
tags: [python, testing, pytest, fixtures, test-data]
---

# Use Factory Fixtures for Varied Test Data

## Description

When tests need the same kind of object with different attributes, return a factory function from the fixture instead of a fixed instance. A fixed fixture forces a new fixture per variation (`user`, `admin_user`, `inactive_user`, ...), while a factory keeps the defaults in one place and lets each test state only the attributes it cares about, which also documents what the test depends on.

## Bad Example

```python
@pytest.fixture
def user() -> User:
    return User(name="alice", email="alice@example.com", active=True, role="member")


@pytest.fixture
def admin_user() -> User:
    return User(name="bob", email="bob@example.com", active=True, role="admin")


@pytest.fixture
def inactive_user() -> User:
    return User(name="carol", email="carol@example.com", active=False, role="member")


# a fixture explosion, and tests can't create two users with chosen attributes
```

## Good Example

```python
@pytest.fixture
def make_user() -> Callable[..., User]:
    counter = itertools.count()

    def _make(*, name: str | None = None, active: bool = True, role: str = "member") -> User:
        name = name or f"user{next(counter)}"
        return User(name=name, email=f"{name}@example.com", active=active, role=role)

    return _make


def test_admin_can_delete_posts(make_user: Callable[..., User]) -> None:
    admin = make_user(role="admin")  # only the relevant attribute is stated

    assert can_delete_posts(admin)


def test_users_have_unique_emails(make_user: Callable[..., User]) -> None:
    assert make_user().email != make_user().email
```

When the objects need cleanup, the factory records what it created and removes it after `yield`:

```python
@pytest.fixture
def create_user(db: Database) -> Iterator[Callable[..., User]]:
    created: list[User] = []

    def _create(*, name: str = "alice", email: str = "alice@example.com") -> User:
        user = User(name=name, email=email)
        db.save(user)
        created.append(user)
        return user

    yield _create

    for user in created:  # runs even when the test fails
        db.delete(user)
```

## Notes

- Use keyword-only parameters in the factory, so call sites stay self-documenting and a reordered parameter cannot silently swap two values.
- Attributes a test doesn't mention get valid defaults; a test must not depend on them. When it does, it states them.
- Type the fixture as `Callable[..., User]` (or a `Protocol` with the exact keyword signature when the parameters matter to the type checker); a `yield` factory returns `Iterator[Callable[..., User]]`.
- A long Arrange step that builds several related objects is a sign a factory is missing.
- A factory of rows in a real database flushes and never commits, inside the per-test rolled-back session (the web-application skill's sqlalchemy-test-rollback).
