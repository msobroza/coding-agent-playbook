---
id: python-enums
name: Enums for closed sets
description: "Model a closed set of options as an Enum, or a Literal in a signature, never as bare strings, and dispatch on it with match and a raising fallback."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: classes
priority: 64
tags: [python, design, typing]
---

# Use Enums for closed sets of options

## Description

A string offers no safety: a typo, a capitalization slip or a translated value silently takes the wrong branch, and nothing fails. When a value can only be one of a fixed set (pipeline stages, order statuses, configuration choices), define an `Enum`, or use a `Literal` in a signature, so the type checker rejects an unknown value before the code runs. Status codes, stages and modes are the usual candidates: anywhere you would otherwise compare against string constants.

## Bad Example

```python
def play(choice: str) -> Outcome:
    if choice == "rock":
        return beats_scissors()
    elif choice == "paper":
        return beats_rock()
    elif choice == "scisssors":  # the typo never matches and nothing reports it
        return beats_paper()
    return Outcome.DRAW  # "Rock" and "papier" end up here silently
```

## Good Example

```python
from collections.abc import Sequence
from enum import Enum
from typing import Literal


class Move(Enum):
    ROCK = "rock"
    PAPER = "paper"
    SCISSORS = "scissors"


def play(choice: Move) -> Outcome:
    match choice:
        case Move.ROCK:
            return beats_scissors()
        case Move.PAPER:
            return beats_rock()
        case Move.SCISSORS:
            return beats_paper()
        case _:
            raise ValueError(f"expected a Move member, got {choice!r}")


play(Move.SCISORS)  # the type checker flags the unknown member
play("rock")  # and the bare string


def export(rows: Sequence[Row], *, fmt: Literal["csv", "json"] = "csv") -> str: ...


move = Move(raw_value)  # parse text once at the edge: raises ValueError on an unknown value
```

## Notes

- An Enum fits a set the code branches on or stores; a `Literal` is enough for a small set of keyword options in one signature.
- Signs to look for: a string or integer parameter that accepts only some values, and `if`/`elif` chains comparing against string literals.
- Values that cross a text boundary (JSON, a database column, a CLI flag): on Python 3.11 and later `StrEnum` members compare and format as their strings; before 3.11, `class Move(str, Enum)` does the same. Convert text to a member once where it enters, with `Move(value)`.
- Compare members by identity or equality (`choice is Move.ROCK`), never by their `.value` strings scattered through the code.
- End every `match` on an Enum with a raising `case _` so a new member cannot fall through silently.
- A closed set of modes with transitions between them is design-state (design-patterns skill).
- The house style keeps the one-line rule (an `Enum` or `Literal` for a closed set); this rule is its long form.
