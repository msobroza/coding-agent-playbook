---
id: design-command
name: Command
description: "When actions must be undone, batched, queued or replayed, make each action a function that performs it and returns an undo closure built from a snapshot; a batch undoes the done steps in reverse and re-raises when one fails."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: specialized-patterns
priority: 89
tags: [python, design, patterns]
---

# Command

## Description

Direct method calls give no control over an action once it runs: it cannot be undone, grouped with others into one all-or-nothing batch, deferred or logged for replay. The command pattern makes each action a value. The lightest Pythonic form is a function that performs the action and returns a zero-argument undo closure; the closure captures what it needs to restore. Capture that state before acting (a snapshot) rather than computing an inverse that may not exist.

## Bad Example

```python
def rename_and_reset(doc: Document) -> None:
    doc.set_title("Quarterly review")
    doc.clear()  # the old title and text are gone: nothing can be undone
```

## Good Example

```python
Undo = Callable[[], None]
Command = Callable[[], Undo]


def change_title(doc: Document, title: str) -> Undo:
    old_title = doc.title  # snapshot before acting
    doc.set_title(title)

    def undo() -> None:
        doc.set_title(old_title)

    return undo


def clear_text(doc: Document) -> Undo:
    old_text = doc.text
    doc.clear()

    def undo() -> None:
        doc.set_text(old_text)

    return undo


def run_batch(commands: Sequence[Command]) -> Undo:
    """Run every command or none: on failure, undo the done ones and re-raise."""
    undos: list[Undo] = []

    def undo_all() -> None:
        for undo in reversed(undos):
            undo()

    try:
        for command in commands:
            undos.append(command())
    except Exception:
        undo_all()
        raise
    return undo_all


undo = run_batch([partial(change_title, doc, "Quarterly review"), partial(clear_text, doc)])
```

## Notes

- Undo a batch in reverse order; when step N fails, undo steps N-1 down to 1 before re-raising, so the caller sees the original error and an unchanged document.
- `contextlib.ExitStack.callback` registers cleanups that run in reverse order, which fits setup steps that must be rolled back together.
- Promote to command dataclasses with `execute` and `undo` methods when commands must be inspected, serialized, stored in a queue or a history, or when their lifecycle grows beyond execute and undo; closures are opaque and do not pickle.
- Signals: undo or redo, queued or scheduled actions, an audit trail, all-or-nothing batches, recorded macros, or a UI that must trigger an action without knowing what it does.
- Stop when nothing is ever reversed, deferred or replayed: call the method.
- The class-based walkthrough with undo and redo stacks and partial batches: see command-progression.md.
