# Python version idioms

Which form each version-dependent idiom takes on this repository's lowest supported Python, and which rule shows it. This page only routes: the rules hold the examples and the reasons.

The floor is the lower bound of `requires-python` in `pyproject.toml`. Template rules render the branch for that floor; with no `requires-python` they render their Python 3.10 branch, and rules gated on a `python_version` do not render at all.

## How to use this page

- Writing code: use the floor's form, even when your local interpreter is newer. The newer form fails, or behaves differently, on the oldest Python the project supports.
- Reviewing code: a form newer than the floor is a finding, unless the same change raises the floor.
- Raising the floor: upgrade the forms in the code the change touches, not the whole repository at once. When the repository's ruff selects the `UP` rules and its `target-version` follows the floor, ruff flags the old forms: UP040, UP046 and UP047 for the 3.12 type syntax, UP017 for `datetime.UTC` and UP041 for the timeout error alias.

## 3.10: the lowest branch

Every rule's examples work on Python 3.10. These idioms already need it:

| Idiom | Rule |
| --- | --- |
| `match` with a raising `case _` | python-match-fallback, python-match-destructuring (both gated on Python 3.10 and later) |
| `X \| None` instead of `Optional[X]` | python-typing |
| `ParamSpec` in a typed decorator | python-decorators |
| `contextlib.aclosing` around an async generator | python-async-generators (gated on Python 3.10 and later) |
| Several context managers in one parenthesized `with (...)` | python-context-managers |

## 3.11

| Idiom | Up to 3.10 | From 3.11 | Rule |
| --- | --- | --- | --- |
| A method returning its own class | a bound `TypeVar`, or the class name in quotes | `typing.Self` | python-typing (template), pydantic-model-validators (Note) |
| Awaiting independent tasks together | `asyncio.gather` | `asyncio.TaskGroup` | python-async, python-async-tasks, python-async-fanout (templates) |
| Handling several task failures | the first error that `gather` raises | `except*` on the `ExceptionGroup` | python-async |
| One deadline for a group of awaits | `asyncio.wait_for` | `async with asyncio.timeout(...)` | python-async, python-async-fanout |
| The timeout error | `asyncio.TimeoutError` | the builtin `TimeoutError` | python-async |
| String-valued options | `class Mode(str, Enum)` | `StrEnum` | python-enums (Note) |
| Exhaustive `match` check | `typing_extensions.assert_never` | `typing.assert_never` | python-match-fallback (Note) |
| A timezone-aware UTC now | `timezone.utc` | `datetime.UTC` | python-pure-core |
| Reading TOML | the `tomli` package | `tomllib` | no rule of this skill; propose a new dependency, never add one unasked |

On 3.10, `except TimeoutError` does not catch the error that `asyncio.wait_for` raises: name `asyncio.TimeoutError` there.

## 3.12

| Idiom | Up to 3.11 | From 3.12 | Rule |
| --- | --- | --- | --- |
| A generic function or class | a module-level `TypeVar` | `def first[T](...)`, `class Cache[K, V]` | python-typing (template) |
| A named type alias | a plain assignment | the `type` statement | python-typing (template); python-type-aliases keeps plain assignment on every version |
| Marking an overriding method | nothing, or `typing_extensions.override` | `typing.override` | no rule of this skill |

## 3.13 and later

No rule renders a branch above 3.12. Use `typing.TypeIs`, type parameter defaults or `warnings.deprecated` only when the floor allows them and the change needs them.

## Gate or branch

- A `python_version` gate means the topic does not exist below that version: `match` statements need 3.10, so their rules do not render for an older floor.
- A template renders on every version and swaps its examples for the floor's form, as python-typing and the asyncio rules do.
- A Note names the newer form beside a 3.10 example, as python-enums and pydantic-model-validators do.

Related guides: choosing-a-data-shape.md, error-flow.md.
