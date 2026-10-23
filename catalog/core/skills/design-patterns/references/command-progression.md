# Command: undo stacks, batches and replay

The class-based command pattern in full, for `design-command`: command objects with `execute` and `undo`, a controller with an undo stack, batches that roll back when a step fails, and a redo stack; then the same operations as functions that return undo closures. Reach for the classes when undo needs a stack with redo, a batch needs rollback, or commands must be stored, inspected or replayed.

## Contents

- The receiver
- Command objects
- A controller with an undo stack
- Batches
- Batch rollback on failure
- A redo stack
- The functional form: undo closures
- Direct use of the functional commands
- Batches of functional commands
- Choosing a form

## The receiver

Every example edits this document:

```python
@dataclass
class Document:
    title: str
    text: str = ""

    def append(self, text: str) -> None:
        self.text += text

    def set_text(self, text: str) -> None:
        self.text = text

    def clear(self) -> None:
        self.text = ""

    def set_title(self, title: str) -> None:
        self.title = title
```

## Command objects

A `Command` Protocol with `execute` and `undo`, and one small class per operation. Each command holds its receiver and its arguments. A command that destroys information snapshots the old state in `execute`, before it changes anything, so `undo` restores the snapshot instead of computing an inverse.

```python
class Command(Protocol):
    def execute(self) -> None: ...
    def undo(self) -> None: ...


@dataclass
class AppendText:
    doc: Document
    text: str
    _before: str = ""

    def execute(self) -> None:
        self._before = self.doc.text
        self.doc.append(self.text)

    def undo(self) -> None:
        self.doc.set_text(self._before)


@dataclass
class ClearText:
    doc: Document
    _before: str = ""

    def execute(self) -> None:
        self._before = self.doc.text
        self.doc.clear()

    def undo(self) -> None:
        self.doc.set_text(self._before)


@dataclass
class ChangeTitle:
    doc: Document
    title: str
    _before: str = ""

    def execute(self) -> None:
        self._before = self.doc.title
        self.doc.set_title(self.title)

    def undo(self) -> None:
        self.doc.set_title(self._before)
```

## A controller with an undo stack

The controller runs commands and remembers them. It knows only the Protocol, so a new command needs no change here.

```python
@dataclass
class EditHistory:
    _done: list[Command] = field(default_factory=list)

    def execute(self, command: Command) -> None:
        command.execute()
        self._done.append(command)

    def undo(self) -> None:
        if self._done:
            self._done.pop().undo()

    def undo_all(self) -> None:
        while self._done:
            self.undo()
```

```python
history = EditHistory()
notes = Document(title="Meeting notes")
history.execute(AppendText(notes, "Started at nine."))
history.execute(ChangeTitle(notes, "Quarterly review"))
history.undo()  # notes.title == "Meeting notes", the text is kept
history.undo_all()  # notes.text == ""
```

## Batches

A batch is itself a command: it executes its commands in order and undoes them in reverse, so the most recent change unwinds first. Batches nest, and the controller still sees one command.

```python
@dataclass
class Batch:
    commands: Sequence[Command]

    def execute(self) -> None:
        for command in self.commands:
            command.execute()

    def undo(self) -> None:
        for command in reversed(self.commands):
            command.undo()
```

## Batch rollback on failure

When a command in the middle of a batch fails, the plain batch leaves the earlier commands applied. Undo the ones already done, newest first, and re-raise, so the caller sees the original error and an unchanged document:

```python
@dataclass
class AtomicBatch:
    commands: Sequence[Command]

    def execute(self) -> None:
        done: list[Command] = []
        try:
            for command in self.commands:
                command.execute()
                done.append(command)
        except Exception:
            for command in reversed(done):
                command.undo()
            raise

    def undo(self) -> None:
        for command in reversed(self.commands):
            command.undo()
```

## A redo stack

Undoing a command moves it to a redo stack; redoing executes it again and moves it back. Any new command clears the redo stack, because the history it described no longer exists.

```python
@dataclass
class EditHistory:
    _done: list[Command] = field(default_factory=list)
    _undone: list[Command] = field(default_factory=list)

    def execute(self, command: Command) -> None:
        command.execute()
        self._done.append(command)
        self._undone.clear()

    def undo(self) -> None:
        if self._done:
            command = self._done.pop()
            command.undo()
            self._undone.append(command)

    def redo(self) -> None:
        if self._undone:
            command = self._undone.pop()
            command.execute()
            self._done.append(command)
```

Re-executing must be safe: each command snapshots again in `execute`, so a redone command restores the right state when it is undone a second time.

## The functional form: undo closures

Each operation becomes a function that performs it at once and returns a zero-argument closure that reverses it. The closure captures the snapshot from the enclosing scope, so no class is needed.

```python
Undo = Callable[[], None]
CommandFunction = Callable[[], Undo]


def append_text(doc: Document, text: str) -> Undo:
    before = doc.text
    doc.append(text)

    def undo() -> None:
        doc.set_text(before)

    return undo


def change_title(doc: Document, title: str) -> Undo:
    before = doc.title
    doc.set_title(title)

    def undo() -> None:
        doc.set_title(before)

    return undo
```

## Direct use of the functional commands

Call a command function, keep the undo it returns, and call the undo when the change must be reversed. No controller is needed: the undo function is the only artifact.

```python
notes = Document(title="Meeting notes")
undo_append = append_text(notes, "Started at nine.")
undo_title = change_title(notes, "Quarterly review")
undo_title()  # notes.title == "Meeting notes"
```

A list of undo functions is the undo stack: append each one, and pop and call the last to undo.

## Batches of functional commands

`functools.partial` turns each call into a zero-argument `CommandFunction`; the batch runs them, collects their undos, and rolls back the done ones when one fails:

```python
def run_batch(commands: Sequence[CommandFunction]) -> Undo:
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


undo = run_batch(
    [
        partial(append_text, notes, " Ended at ten."),
        partial(change_title, notes, "Quarterly review"),
    ]
)
undo()  # both changes reversed, newest first
```

## Choosing a form

| Need | Form |
| --- | --- |
| Undo one action, or a batch, right after it ran | undo closures |
| Undo and redo through a history | command objects and a controller |
| Store, inspect, serialize or replay commands | command objects (closures are opaque and do not pickle) |
| A batch that must apply fully or not at all | either form, with rollback of the done steps |
| Nothing is ever reversed, deferred or replayed | call the method directly |
