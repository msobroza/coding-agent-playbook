---
id: design-single-responsibility
name: Single responsibility
description: "Give each module, class and function one job and one reason to change; split along the responsibilities a unit mixes."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: responsibilities
priority: 40
tags: [python, design, solid]
---

# Single responsibility

## Description

Each module and class has one job and one reason to change. That lets any reader, a person or an agent, load just the unit it needs, test it on its own, edit it without side effects elsewhere, and find it by searching for its responsibility. Tangled responsibilities force a reader to load far more context for a small change: one 800-line class doing three jobs costs more than three 250-line classes of the same total size. When a unit handles several responsibilities, a change to one of them can break the others, so the unit is harder to maintain and to test.

## Bad Example

```python
class UserManager:
    def __init__(self, db: Connection, smtp: SmtpClient) -> None:
        self._db = db
        self._smtp = smtp

    def create_user(self, email: str, display_name: str) -> User:
        # Responsibility 1: validation
        if "@" not in email:
            raise InvalidEmailError(email)
        # Responsibility 2: database operations
        self._db.execute("INSERT INTO users VALUES (?, ?)", (email, display_name))
        # Responsibility 3: email notification
        self._smtp.send(to=email, subject="Welcome", body=f"Hello {display_name}")
        return User(email=email, display_name=display_name)
```

## Good Example

```python
class UserRepository:
    def __init__(self, db: Connection) -> None:
        self._db = db

    def save(self, user: User) -> None:
        self._db.execute("INSERT INTO users VALUES (?, ?)", (user.email, user.display_name))


class WelcomeMailer:
    def __init__(self, smtp: SmtpClient) -> None:
        self._smtp = smtp

    def send_welcome(self, user: User) -> None:
        self._smtp.send(to=user.email, subject="Welcome", body=f"Hello {user.display_name}")


def validate_email(email: str) -> None:
    if "@" not in email:
        raise InvalidEmailError(email)


class UserService:
    def __init__(self, repository: UserRepository, mailer: WelcomeMailer) -> None:
        self._repository = repository
        self._mailer = mailer

    def create_user(self, email: str, display_name: str) -> User:
        validate_email(email)
        user = User(email=email, display_name=display_name)
        self._repository.save(user)
        self._mailer.send_welcome(user)
        return user
```

## Notes

- Warning signs: describing the unit needs the word "and", its module imports from unrelated layers, or its private helpers form groups around different attributes. Split along those lines, so each part can be tested on its own.
- Each collaborator now changes for one reason: a new mail template never touches the SQL.
- The same applies to functions: extract a function when one does two things, and split a function that branches on a type flag into one function per branch only when the flag picks a different algorithm (python-function-signatures in the python-coding skill covers flag parameters).
- Keeping I/O out of the model, so it returns data and the caller prints or stores it, is `python-pure-core` in the python-coding skill.
- A collaborator that holds dependencies is a plain class; a dataclass is for records.
- Splitting a class whose methods cluster around disjoint attributes, step by step, is `design-split-god-class`.
- Exceptions: a facade or coordinator has low cohesion by design, because its job is to sequence others; keep it thin rather than splitting it. Short scripts and notebooks need no split.
