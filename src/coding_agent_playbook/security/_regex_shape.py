"""The structure check behind ``secrets.screen_regex`` (specs/prK-hook-pack.md §E.4).

Walks the parse tree of CPython's own regex parser, ``re._parser``. It is
private, but present and stable on every supported version (3.12, 3.13); the
public alias ``sre_parse`` raises a DeprecationWarning on import, which the
suite's ``filterwarnings = error`` turns into a failure. The module is loaded
through ``importlib`` because typeshed ships no ``re._parser`` stub.
``tests/security/test_secrets.py`` pins the parser it relies on.
"""

from __future__ import annotations

import importlib
from typing import Final

__all__ = ["has_nested_unbounded_repeat"]

_PARSER: Final = importlib.import_module("re._parser")
#: The repeat opcodes (``POSSESSIVE_REPEAT`` exists from 3.11).
_REPEATS: Final = frozenset(
    op
    for op in (
        _PARSER.MAX_REPEAT,
        _PARSER.MIN_REPEAT,
        getattr(_PARSER, "POSSESSIVE_REPEAT", None),
    )
    if op is not None
)
_UNBOUNDED: Final[int] = _PARSER.MAXREPEAT


def has_nested_unbounded_repeat(pattern: str) -> bool:
    """Whether an unbounded repeat (``*``, ``+``, ``{n,}``) sits inside another.

    Raises ``re.error`` for a pattern that does not parse.

    Example::

        >>> has_nested_unbounded_repeat("(a+)+$"), has_nested_unbounded_repeat("a+b+")
        (True, False)
    """
    return _nested(_PARSER.parse(pattern), inside=False)


def _nested(subpattern: object, *, inside: bool) -> bool:
    for op, av in _items(subpattern):
        unbounded = op in _REPEATS and av[1] == _UNBOUNDED
        if unbounded and inside:
            return True
        if any(_nested(child, inside=inside or unbounded) for child in _children(av)):
            return True
    return False


def _items(subpattern: object) -> list[tuple[object, tuple[object, ...]]]:
    data = getattr(subpattern, "data", ())
    return [(item[0], item[1]) for item in data]


def _children(av: object) -> list[object]:
    """The sub-patterns nested anywhere in an opcode's argument."""
    if isinstance(av, _PARSER.SubPattern):
        return [av]
    if isinstance(av, (tuple, list)):
        return [child for part in av for child in _children(part)]
    return []
