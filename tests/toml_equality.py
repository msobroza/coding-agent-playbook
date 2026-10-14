"""Type-strict equality for parsed TOML values, shared by the writer round-trip tests.

``playbook init`` writes the committed tables ``Config`` does not manage back with
the *same parsed values*, and Python ``==`` is too lenient to pin that: ``True ==
1 == 1.0``, ``-0.0 == 0.0``, two aware datetimes naming the same instant compare
equal across offsets, and ``nan != nan``. A writer turning ``weight = 1.0`` into
``weight = 1`` passed every ``==`` round-trip test. :func:`toml_mismatch` compares
exact types at every level, floats by value *and* sign (NaN-aware), and
datetimes/times by ``utcoffset()`` and ``isoformat()``. Table key order is not
compared: the writer puts a table's own keys before its sub-tables.

The walk is iterative, so it compares documents nested deeper than Python's
recursion limit (the writer's own deep-nesting tests).
"""

from __future__ import annotations

import datetime as dt
import math

#: One pair still to compare: its location (``$.links.allowed_domains[0]``) and both values.
_Pair = tuple[str, object, object]


def toml_mismatch(actual: object, expected: object) -> str | None:
    """The first difference between two parsed TOML values, or ``None`` when identical.

    Example::

        >>> toml_mismatch({"w": 1.0}, {"w": 1.0}) is None
        True
        >>> toml_mismatch({"w": 1}, {"w": 1.0})
        '$.w: int 1 is not float 1.0'
    """
    pending: list[_Pair] = [("$", actual, expected)]
    while pending:
        path, got, want = pending.pop()
        problem = _node_mismatch(path, got, want)
        if problem is not None:
            return problem
        pending.extend(_child_pairs(path, got, want))
    return None


def assert_toml_identical(actual: object, expected: object) -> None:
    """Fail with the first :func:`toml_mismatch`, so the message names where it is."""
    problem = toml_mismatch(actual, expected)
    assert problem is None, problem


def _node_mismatch(path: str, got: object, want: object) -> str | None:
    """What differs at this node itself (type, key set, length or leaf value)."""
    if type(got) is not type(want):
        return f"{path}: {type(got).__name__} {got!r} is not {type(want).__name__} {want!r}"
    if isinstance(got, dict) and isinstance(want, dict):
        if got.keys() != want.keys():
            return f"{path}: keys {sorted(got)} != {sorted(want)}"
        return None
    if isinstance(got, list) and isinstance(want, list):
        return None if len(got) == len(want) else f"{path}: {len(got)} items != {len(want)}"
    return None if _same_leaf(got, want) else f"{path}: {got!r} != {want!r}"


def _child_pairs(path: str, got: object, want: object) -> list[_Pair]:
    """The pairs one level down; called only after :func:`_node_mismatch` passed."""
    if isinstance(got, dict) and isinstance(want, dict):
        return [(f"{path}.{key}", got[key], want[key]) for key in want]
    if isinstance(got, list) and isinstance(want, list):
        return [
            (f"{path}[{index}]", a, b) for index, (a, b) in enumerate(zip(got, want, strict=True))
        ]
    return []


def _same_leaf(got: object, want: object) -> bool:
    """Leaf equality for two values of the same type."""
    if isinstance(got, float) and isinstance(want, float):
        same_sign = math.copysign(1.0, got) == math.copysign(1.0, want)
        return same_sign and (got == want or (math.isnan(got) and math.isnan(want)))
    if isinstance(got, (dt.datetime, dt.time)) and isinstance(want, (dt.datetime, dt.time)):
        return got.utcoffset() == want.utcoffset() and got.isoformat() == want.isoformat()
    return got == want
