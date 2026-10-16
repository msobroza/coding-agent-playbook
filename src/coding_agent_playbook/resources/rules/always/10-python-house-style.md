---
id: python-house-style
name: Python house style
description: Repo-wide Python conventions that apply to every file you touch.
version: 1
scope: always
priority: 10
tags: [always, python, style]
---

# Python house style

Conventions that apply to every Python file. Follow them in new code; when editing existing code, follow the surrounding style if it differs and the file would become inconsistent.

## Paths and I/O

- Use `pathlib.Path` for filesystem paths. Reach for `os.path` only when calling out to legacy stdlib that requires a `str`.
- Open files via `Path.read_text(encoding="utf-8")` / `Path.write_text(...)`. Pass `encoding=` explicitly — the platform default has bitten too many cross-platform repos.

## Data shapes

- Structured data: use `@dataclass` (frozen when immutable). Reach for Pydantic at I/O boundaries (request bodies, config files, anything crossing a serialization seam).
- Avoid dict-of-strings as a stand-in for a record type. If three or more fields belong together, give them a dataclass. Pass typed records between layers, never `dict[str, Any]`.
- A frozen dataclass is only shallowly immutable: give it `tuple`/`frozenset` fields and copy collections passed in, including from a builder into the object it builds.
- No parallel lists indexed together; zip them into one list of records. Return at most three values as a tuple, otherwise a dataclass or `NamedTuple`. Compute derived values with `@property` instead of storing a copy that can go stale.
- Money is never `float`: use `Decimal` or integer minor units (cents).
- Name domain magic values as `UPPER_CASE` module constants annotated `Final`, beside the code that uses them. Values that change per environment (URLs, credentials, feature flags, deployment-tuned timeouts) live in the single settings object.

## Function signatures

- Type-hint every function signature, private helpers included.
- Never use a mutable default argument (`[]`, `{}`, `set()`); default to `None`, or `field(default_factory=...)` in a dataclass.
- Make boolean option flags keyword-only (`*, dry_run: bool = False`). When a flag selects a different algorithm, split the function instead.
- Use an `Enum`/`StrEnum` (or `Literal[...]` in a signature) for a closed set of options, never bare string constants.
- Prefer composition over inheritance. Subclass only when the relationship is genuinely substitutable.
- Never subclass a third-party class to change its interface; wrap it. Framework base classes (`BaseModel`, `BaseSettings`, `DeclarativeBase`, Django views), exception hierarchies and documented ABC extension points are normal subclassing.

## Strings and formatting

- Use f-strings (`f"hello, {name}"`). Avoid `%`-formatting and `.format()`.
- Double-quoted strings for prose, single-quoted only when the string contains a double quote. Ruff/Black settle this for you when configured — don't fight the formatter.

## Imports

Group in this order, separated by a blank line:

1. Standard library
2. Third-party
3. First-party (this repo's packages)

```python
import json  # stdlib
from pathlib import Path

import httpx  # third-party

from myapp.orders import place_order  # first-party
```

## Small but persistent annoyances

- Don't `from foo import *`. Name what you use.
- Don't shadow builtins (`list`, `dict`, `id`, `type`, `vars`) with local variables.
- Prefer early `return` over deeply nested `if`/`else`.
- Never write a bare `# noqa`. Write `# noqa: CODE` plus a comment saying why, the same discipline as `# type: ignore[code]`.
- Follow the repo's existing layout axis (layer-first or feature-first), and never mix the two.

## Examples

Good:

```python
from pathlib import Path


def count_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())
```

Avoid:

```python
def count_lines(path):  # missing type hints
    return len(open(path).read().splitlines())  # no encoding, no Path, leaked file handle
```
