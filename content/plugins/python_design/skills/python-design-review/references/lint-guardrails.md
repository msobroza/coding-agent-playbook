# Lint guardrails

Many smells in this skill have a ruff rule that catches them on every commit, which is cheaper than finding them in review. When a review turns up a smell more than once, suggest the matching rule.

**Never edit a project's lint configuration unless asked.** Propose the change in the review, with the rules it adds and the number of existing violations it would surface, and let the owners decide. Enabling a rule on a large codebase usually needs a baseline (per-file ignores or a cleanup pass) first.

## Rules worth enabling

| Rule | Catches | Smell id |
| --- | --- | --- |
| `E722` | bare `except:` | bare-except |
| `BLE001` | `except Exception` that neither re-raises nor logs the traceback | swallowed-exception |
| `S110`, `S112` | `try`/`except` whose body is only `pass` or `continue` | swallowed-exception |
| `B904` | `raise` inside `except` without `from` | (lost cause chain) |
| `B006` | mutable default argument | mutable-default-argument |
| `B008` | function call in a default argument | (shared default) |
| `B019` | `functools.cache` or `lru_cache` on a method | method-cache |
| `RUF012` | mutable class attribute default | (shared mutable state) |
| `FBT001`, `FBT002`, `FBT003` | positional boolean parameters and boolean literals passed positionally | boolean-flag-parameter |
| `PLR0913` | too many parameters (default limit 5) | long-parameter-list |
| `C901`, `PLR0912`, `PLR0915` | complex functions, too many branches or statements | long-function, deep-nesting |
| `SIM115` | `open()` outside a `with` block | missing-with |
| `ASYNC` | blocking calls (HTTP, `open`, `time.sleep`) inside `async def` | (event-loop stalls) |
| `RUF006` | `asyncio.create_task` result not stored, so the task can be collected mid-flight | (lost task) |
| `DTZ` | `datetime.now()` and `utcnow()` without a timezone | naive-datetime |
| `A001`, `A002` | variables and parameters shadowing builtins | shadowed-builtin |
| `PLW0603` | the `global` statement | module-level-mutable-global-rebound |
| `SLF001` | access to another object's private members | private-access |
| `F403` | `from module import *` | wildcard-import |

Notes:

- The `FBT` rules flag only positional booleans, which matches the convention that option flags are keyword-only. A keyword-only flag passes; an algorithm switch still needs a human to split it.
- `B008` fires on `Depends(...)` in FastAPI parameter defaults. Use `Annotated` dependency aliases, which avoid the call in the default, or list the framework calls under `lint.flake8-bugbear.extend-immutable-calls`.
- `PLR0913` honors `@typing.override`, so overrides of a wide base signature are not flagged twice. Its limit lives in `lint.pylint.max-args`.
- `PLR6301` (method could be a function) and `PLR0917` (too many positional parameters) exist but are preview-only. Suggest them only to projects that already run ruff with preview enabled.
- Do not enable `TRY003` (long messages passed to exception constructors). It pushes toward generic messages, while a good error message names the offending value and the expected shape.
- `PLR2004` (magic values in comparisons) is noisy on test code. When suggested, scope it to source directories.

## Suggesting the change

Show the proposal as a snippet the owners can paste, adding to the existing selection rather than replacing it:

```toml
[tool.ruff.lint]
extend-select = ["E722", "BLE001", "S110", "S112", "B904", "B006", "B019", "FBT", "PLR0913", "SIM115", "ASYNC", "RUF006", "DTZ"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["FBT", "PLR0913"]
```

Mention that `ruff check --statistics` with the proposed selection reports how many violations already exist, so the owners can size the cleanup before turning the rules on.
