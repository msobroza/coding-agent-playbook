---
id: python-pure-core
name: Pure core
description: "Keep business logic free of I/O, clocks, randomness and hidden mutation; perform effects in a thin outer shell."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: effects
priority: 49
tags: [python, design, testability]
---

# Pure core, effects at the edges

Logic that depends only on its arguments is tested with plain input-to-output assertions and reused anywhere. Keep domain and calculation code pure, and let a thin outer shell gather inputs, call it, and carry out the effects. Small scripts and notebooks may stay imperative.

## Inputs arrive as arguments

- A domain or calculation function never reads the wall clock (`datetime.now()`, `time.time()`), randomness (`random`, `uuid4()`), environment variables or files on its own. Pass the value in, or pass a clock (`now: Callable[[], datetime]`), an id factory or a `random.Random` instance when it needs fresh ones.
- When one function reads input, computes, and presents the result, split it so the computing step runs without patching anything.

## Effects stay in the shell

- Domain classes contain no `print()`, `input()`, network, file or mail I/O. Return values; the entry point or handler presents or persists them.
- Render for humans with `__str__`, `__format__` or a separate presenter, not with `show_*()` methods that print.
- `__init__` does no I/O, printing or registration, and starts no threads or tasks.

## No hidden mutation

- Don't mutate arguments or module-level state, and never share state through a `global` statement. Return a new value (`dataclasses.replace(...)`, a new list).
- When in-place mutation is the contract, make the name say so (`sort_in_place`, `apply_discount_to`) and return `None`.

## Testing the core

Test pure functions with direct argument-to-return assertions and no mocks. Freeze-time libraries (freezegun, time-machine) are for characterizing legacy code that cannot take a clock yet, not a substitute for passing one in new code.

```python
def is_expired(token: Token, now: datetime) -> bool:  # good: caller supplies the time
    return token.expires_at <= now


def is_expired_legacy(token: Token) -> bool:  # avoid: testable only by freezing time
    return token.expires_at <= datetime.now(UTC)
```
