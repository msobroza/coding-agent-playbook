---
id: design-dry-yagni-kiss
name: DRY, YAGNI and KISS
description: "Give each piece of knowledge one home, build nothing a present need does not ask for, and pick the simplest design that works."
scope: scoped
globs:
  - "**/*.py"
section: simplicity
priority: 50
tags: [python, design, simplicity]
---

# DRY, YAGNI and KISS

## Description

Three principles keep a design no bigger than its problem. DRY: each piece of knowledge (a rule, a format, a validation) lives in one place, so a change happens once. YAGNI: build only what a stated requirement needs today; speculative options and hooks add code to read, test and maintain, and often never get used. KISS: of two designs that work, pick the simpler one. Every reader benefits, people and agents alike: a change to logic that lives in several copies has to find every copy, and copies that drifted apart do not all match the same search, so one gets fixed and the others stay stale.

## Bad Example

```python
def create_user(email: str) -> User:
    if not email or "@" not in email:
        raise InvalidEmailError(f"invalid email {email!r}: expected an address containing '@'")
    return User(email=email)


def update_email(user: User, email: str) -> None:
    if not email or "@" not in email:  # the same rule, copied
        raise InvalidEmailError(f"invalid email {email!r}: expected an address containing '@'")
    user.email = email


class ReportExporter:
    def __init__(
        self,
        format: str = "json",  # shadows the builtin
        compression: str | None = None,  # nobody asked for these
        encryption: str | None = None,
        cache_enabled: bool = False,
    ) -> None: ...


class StringReverser:  # a class around one expression
    def reverse(self, text: str) -> str:
        return text[::-1]
```

## Good Example

```python
def validated_email(email: str) -> str:
    if not email or "@" not in email:
        raise InvalidEmailError(f"invalid email {email!r}: expected an address containing '@'")
    return email


def create_user(email: str) -> User:
    return User(email=validated_email(email))


def update_email(user: User, email: str) -> None:
    user.email = validated_email(email)


class ReportExporter:
    def __init__(self, *, output_format: ReportFormat = ReportFormat.JSON) -> None:
        self._output_format = output_format


reversed_title = title[::-1]
```

## Notes

- One home for each piece of logic is what makes a change safe, not a matter of elegance: nothing in a reader's context points from one copy to the others, so an edit to one copy, by a person or an agent, quietly leaves the rest stale.
- DRY is about knowledge, not text: extract when two copies encode the same rule and must change together. Code that only looks alike but changes for different reasons stays separate.
- Extract a shared abstraction when the third real case arrives, not before; a hasty abstraction with many parameters to cover unrelated callers is worse than the copies.
- Add no parameters, options or hooks for needs nobody has stated. YAGNI is not a license for sloppy code: invest in clean structure, not in speculative features.

| Situation | Principle |
| --- | --- |
| The same rule in three places | DRY: extract it |
| "We might need this later" | YAGNI: do not build it |
| Two working solutions | KISS: pick the simpler one |
| An abstraction before its need | YAGNI and KISS: wait for a real case |

- The principles can pull against each other: DRY applied too early breaks YAGNI, and oversimplifying can leave duplicates. When in doubt, start simple and refactor when the repetition is real.
