---
id: python-abstract-inputs
name: Abstract inputs
description: "Type read-only inputs with the broadest collections.abc type the body needs, such as Iterable, Sequence or Mapping, and return concrete types."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: types
priority: 46
tags: [python, typing]
---

# Abstract inputs

## Description

Type each input with the most general type that supports what the body does with it. A parameter typed `list[str]` that the body only iterates rejects a tuple, a set, a generator or a dict's keys for no reason, so callers convert their data just to satisfy the signature. An abstract read-only type from `collections.abc` accepts all of them and also says "this function will not mutate what you pass". Outputs are the opposite: return the concrete type, so callers can index, append or mutate the result freely.

## Bad Example

```python
def count_active(user_ids: list[str], active: set[str]) -> int:
    return sum(1 for user_id in user_ids if user_id in active)


def label_for(code: str, labels: dict[str, str]) -> str:
    return labels.get(code, code)


count_active(list(rows), set(active_ids))  # callers convert to fit the signature
```

## Good Example

```python
from collections.abc import Iterable, Mapping, Sequence, Set


def count_active(user_ids: Iterable[str], active: Set[str]) -> int:
    return sum(1 for user_id in user_ids if user_id in active)


def label_for(code: str, labels: Mapping[str, str]) -> str:
    return labels.get(code, code)


def top_scores(scores: Sequence[int], *, limit: int) -> list[int]:
    return sorted(scores, reverse=True)[:limit]
```

`count_active` now takes a generator, `label_for` a read-only mapping proxy, and `top_scores` returns a list its caller owns.

## Notes

- Pick the input type by what the body does:

  | The body... | Input type |
  | --- | --- |
  | iterates once | `Iterable[T]` |
  | indexes, slices or takes `len` | `Sequence[T]` |
  | looks up by key | `Mapping[K, V]` |
  | tests membership in a set | `Set[T]` (from `collections.abc`) |
  | mutates it in place | the concrete `list[T]`, `dict[K, V]` or `set[T]` |

- `str` is itself a `Sequence[str]`: when a parameter must not accept a single string, keep a narrower type or check at the boundary.
- An `Iterable` can be consumed only once; when the body walks the input twice, take a `Sequence` or convert once at the top.
- Return concrete types (`list`, `dict`, a dataclass), never an abstract one, unless the function deliberately hands back a read-only view.
- A read-only input can default to an immutable empty value (`()`); mutable defaults are `python-typing`'s.
