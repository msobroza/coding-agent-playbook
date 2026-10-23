# Lint guardrails

Many smells in smell-catalog.md have a ruff code that catches them on every commit, which is cheaper than finding them in review. When a review turns up the same smell more than once, name the matching code in the finding. Proposing that the project turn a code on, and sizing the cleanup it would need, is python-tooling's ruff-lint; this file only maps the smell to the code.

| Code | Catches | Smell id | Owning rule |
| --- | --- | --- | --- |
| `E722` | bare `except:` | `bare-except` | python-coding's python-error-handling |
| `BLE001` | `except Exception` that neither re-raises nor logs the traceback | `swallowed-exception` | python-coding's python-error-handling |
| `S110`, `S112` | `try`/`except` whose body is only `pass` or `continue` | `swallowed-exception` | python-coding's python-error-handling |
| `B904` | `raise` inside `except` without `from` | (lost cause chain) | python-coding's python-error-handling |
| `B006` | mutable default argument | `mutable-default-argument` | python-coding's python-typing |
| `B008` | function call in a default argument | (shared default) | python-coding's python-typing |
| `B019` | `functools.cache` or `lru_cache` on a method | `method-cache` | python-coding's python-properties |
| `RUF012` | mutable class attribute default | (shared mutable state) | python-coding's python-typing |
| `FBT001`, `FBT002`, `FBT003` | positional boolean parameters and boolean literals passed positionally | `boolean-flag-parameter` | python-coding's python-function-signatures |
| `PLR0913` | too many parameters (default limit 5) | `long-parameter-list` | `design-start-with-the-data` |
| `C901`, `PLR0912`, `PLR0915` | complex functions, too many branches or statements | `long-function`, `deep-nesting` | python-coding's python-small-units |
| `SIM115` | `open()` outside a `with` block | `missing-with` | python-coding's python-context-managers |
| `ASYNC` | blocking calls (HTTP, `open`, `time.sleep`) inside `async def` | (event-loop stalls) | python-coding's python-async |
| `RUF006` | `asyncio.create_task` result not stored, so the task can be collected mid-flight | (lost task) | python-coding's python-async-tasks |
| `DTZ` | `datetime.now()` and `utcnow()` without a timezone | `naive-datetime` | python-coding's python-pure-core |
| `A001`, `A002` | variables and parameters shadowing builtins | `shadowed-builtin` | python-coding's python-idioms |
| `PLW0603` | the `global` statement | `module-level-mutable-global-rebound` | `design-low-coupling` |
| `SLF001` | access to another object's private members | `private-access` | `design-tell-dont-ask` |
| `F403` | `from module import *` | `wildcard-import` | python-coding's python-imports |

What a code does and does not catch, so a finding names it accurately:

- The `FBT` codes flag only positional booleans, which matches the convention that option flags are keyword-only. A keyword-only flag passes; a flag that picks an algorithm still needs a reader to split it.
- `B008` also fires on a framework's dependency marker called in a parameter default. `Annotated` dependency aliases avoid the call; listing the marker under `lint.flake8-bugbear.extend-immutable-calls` silences it.
- `PLR0913` skips overrides marked `@typing.override`, so a wide base signature is reported once. Its limit is `lint.pylint.max-args`.
- `C901` and `PLR0912` count branches, not nesting depth: a flat function with many guard clauses can trip them while a deeply nested one stays under. detect_smells.py reports deep-nesting itself.
- Many smells have no code: data shapes, feature envy, low cohesion and speculative abstraction are found by reading, guided by quality-checklist.md, and `design-review-by-severity` ranks them.
