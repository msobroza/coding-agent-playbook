---
id: python-idioms
name: Idioms
description: "Keep os.path for legacy str APIs, use f-strings, group imports, split flag-driven functions, and avoid star imports and shadowed builtins."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: idioms
priority: 72
tags: [python, style]
---

# Python idioms

Small conventions that keep Python files uniform. Follow them in new code. When you edit an existing file that does something differently, match the file so it stays consistent.

## Paths and files

The always-loaded house style owns `Path` and the explicit encoding; this section adds only the exception and the call to use.

- `os.path` is acceptable only where a legacy standard-library call needs a `str`.
- Read or write a whole text file with `Path.read_text` and `Path.write_text`, not `open(...).read()`, which leaves the file handle open.

```python
def count_lines(path: Path) -> int:  # good
    return len(path.read_text(encoding="utf-8").splitlines())


def count_lines_legacy(path):  # avoid: no type hints, no encoding, no Path, leaked file handle
    return len(open(path).read().splitlines())
```

## Functions

- When a boolean flag selects a different algorithm, split the function in two instead of branching on the flag.
- Class design (composition, subclassing, protocols) is covered in `python-classes-and-protocols`.

## Strings

- Use f-strings (`f"hello, {name}"`), not `%`-formatting or `.format()`.
- Use double quotes, and single quotes only when the string contains a double quote. Where Ruff or Black is configured, let the formatter decide.

## Imports

Group imports in this order, with a blank line between groups: standard library, third-party, then first-party (this repo's packages). Never write `from module import *`; name what you use.

```python
import json  # standard library
from pathlib import Path

import httpx  # third-party

from myapp.orders import place_order  # first-party
```

## Small things reviewers flag

- Don't shadow builtins (`list`, `dict`, `id`, `type`, `vars`) with local names.
- Guard clauses and shallow nesting are covered in `python-early-return`.
