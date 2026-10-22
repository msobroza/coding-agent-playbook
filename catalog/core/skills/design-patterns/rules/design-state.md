---
id: design-state
name: State
description: "When behavior depends on a mode that changes and the same status checks repeat in many methods, keep the legal transitions in one Enum-keyed table that raises a domain error naming the state and the action; move to state objects only when each state carries substantial behavior."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: specialized-patterns
priority: 84
tags: [python, design, patterns]
---

# State

## Description

An object whose behavior depends on a mode that changes over its life (draft, in review, final) tends to grow the same status guard in every method. The transitions then drift apart: one method forgets a check, another allows a move the rules forbid, and adding a state means editing every method. Keep the rules in one place. The lightest form is an `Enum` of states, an `Enum` of actions and a transition table keyed by `(state, action)`; a missing pair is an illegal transition and raises a domain error that names both the current state and the action.

## Bad Example

```python
class Document:
    def __init__(self) -> None:
        self.status = "draft"
        self.paragraphs: list[str] = []

    def edit(self, text: str) -> None:
        if self.status != "draft":
            raise ValueError("cannot edit")
        self.paragraphs.append(text)

    def submit(self) -> None:
        if self.status != "draft":
            raise ValueError("cannot submit")
        self.status = "review"

    def finalize(self) -> None:
        if self.status == "draft":  # forgot that "final" may not finalize again
            raise ValueError("cannot finalize")
        self.status = "final"
```

## Good Example

```python
class Status(Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    FINAL = "final"


class Action(Enum):
    EDIT = "edit"
    SUBMIT = "submit"
    FINALIZE = "finalize"


TRANSITIONS: Final[Mapping[tuple[Status, Action], Status]] = {
    (Status.DRAFT, Action.EDIT): Status.DRAFT,
    (Status.DRAFT, Action.SUBMIT): Status.IN_REVIEW,
    (Status.IN_REVIEW, Action.FINALIZE): Status.FINAL,
}


class IllegalTransitionError(DocumentError):
    def __init__(self, status: Status, action: Action) -> None:
        super().__init__(f"cannot {action.value} a document in state {status.value}")
        self.status = status
        self.action = action


def next_status(status: Status, action: Action) -> Status:
    try:
        return TRANSITIONS[(status, action)]
    except KeyError:
        raise IllegalTransitionError(status, action) from None
```

Each method of `Document` calls `next_status` first, so every rule lives in the table.

## Notes

- Heavier form: when each state carries substantial behavior, give each state its own class behind a Protocol (`edit`, `submit`, `finalize`) and let the document delegate to its current state object. State methods return the next state or a result; they never print.
- State versus strategy: a strategy is chosen by the caller and stays put; a state changes as the object moves through its life.
- The initial state is set where the object is created; a workflow framework that already tracks states needs no second machine.
- Stop at two states that barely differ: a boolean or a two-member `Enum` is enough.
