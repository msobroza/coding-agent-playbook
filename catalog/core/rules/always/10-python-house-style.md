---
id: python-house-style
name: Python house style
description: The seven Python conventions that hold in every file, new or edited.
scope: always
priority: 10
tags: [always, python, style]
---

- Type-hint every function signature, private helpers included.
- Use `pathlib.Path` for paths, and pass `encoding="utf-8"` whenever you open, read or write text: the platform default differs between machines.
- Pass typed records between layers: a frozen dataclass, Pydantic only at I/O boundaries, never `dict[str, Any]`.
- Never use a mutable default argument; every call shares the one object, so default to `None` (`field(default_factory=...)` in a dataclass). Make boolean flags keyword-only (`*, dry_run: bool = False`). Use an `Enum` or `Literal` for a closed set of options.
- Money is never `float`, which cannot hold most cent values exactly: use `Decimal` or integer minor units (cents).
- Never write a bare `# noqa` or `# type: ignore`, which silences every code: name the code (`# noqa: E501`, `# type: ignore[arg-type]`) and add a comment saying why.
- Wrap a third-party class instead of subclassing it to change its interface (framework base classes excepted).
