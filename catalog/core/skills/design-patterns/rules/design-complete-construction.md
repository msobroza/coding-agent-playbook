---
id: design-complete-construction
name: Complete construction
description: "Hand callers a ready object: no setup call to remember after construction, and no __new__ that returns another type."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: smells
priority: 63
tags: [python, design, construction]
---

# Complete construction

## Description

An object is usable the moment its constructor returns. When a caller must remember a second call (`connect()`, `load()`, `init()`) before the object works (smell id two-step-initialization), forgetting it fails later and far away. Encapsulate the sequence: require the ready inputs in `__init__`, or do the setup in a classmethod constructor that returns a complete instance. Likewise `Cls(...)` should always mean "a `Cls`": a `__new__` that returns some other class depending on its arguments (smell id polymorphic-new) misleads readers and type checkers alike.

## Bad Example

```python
processor = PaymentProcessor()
processor.connect(gateway_url)  # forget this and the first charge fails


class LogReader:
    def __new__(cls, log_format: LogFormat) -> "LogReader":
        if log_format is LogFormat.JSON:
            return JsonLogReader()
        return PlainLogReader()
```

## Good Example

```python
class PaymentProcessor:
    def __init__(self, session: GatewaySession) -> None:
        self._session = session  # stores a ready dependency; no I/O here

    @classmethod
    def connect(cls, gateway_url: str) -> "PaymentProcessor":
        return cls(GatewaySession.open(gateway_url))


processor = PaymentProcessor.connect(gateway_url)


READER_CLASSES: Final[Mapping[LogFormat, type[LogReader]]] = {
    LogFormat.JSON: JsonLogReader,
    LogFormat.PLAIN: PlainLogReader,
}


def make_log_reader(log_format: LogFormat) -> LogReader:
    return READER_CLASSES[log_format]()
```

## Notes

- Keep `__init__` to storing ready-made dependencies and checking invariants. Setup work, printing and I/O move to a classmethod constructor or to the caller (python-coding's python-pure-core keeps I/O out of the core).
- A classmethod constructor (`from_file`, `connect`, `from_settings`) names how the object is built and can raise a domain error before a half-built object exists.
- The signal: documentation or a comment that says "call X before using Y", or a method that raises when an earlier call was skipped.
- A key-to-constructor mapping replaces a `__new__` that switches on its argument; the mapping keyed by a closed `Enum` is design-open-closed, and keys that arrive as data are design-dispatch-table.
- Building collaborators inside `__init__` (`self.client = HttpClient()`) is a different smell: inject them (python-coding's python-dependency-injection).
