"""Path globs compiled once per process into regexes (specs/prK-lifecycle-hooks.md §D.2.4).

The grammar is gitignore-like and matches ``NormalizedPath.key``:

- ``**`` crosses ``/`` (``**/`` also matches zero directories); ``*`` and
  ``?`` never do; ``[...]`` classes work, ``[!...]`` negates.
- A pattern with no ``/`` matches the basename at any depth; one with a
  ``/`` is anchored. A trailing ``/`` means everything under that directory.
- Matching is ``re.fullmatch``, so ``key.pem`` does not match ``key.pem.bak``.

Patterns are folded with the same ``fold_key`` as keys, so a darwin or win32
``.ENV`` matches ``.env*``.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["FOLDING_PLATFORMS", "GlobSet", "compile_globs", "fold_key", "glob_to_regex"]

#: Platforms whose default filesystems compare names case-insensitively (§D.2.4 step 6).
FOLDING_PLATFORMS = frozenset({"darwin", "win32"})

_ANY_DIRS = "(?:.*/)?"
#: Characters escaped inside a class: ``re`` reads them as nested sets or set operators.
_CLASS_SPECIAL = frozenset("\\[&~|")


@dataclass(frozen=True, slots=True)
class GlobSet:
    """A compiled tuple of globs; build one with :func:`compile_globs`.

    Example::

        >>> compile_globs(["*.pem"], platform="linux").matches("certs/key.pem")
        True
    """

    patterns: tuple[str, ...]
    regexes: tuple[re.Pattern[str], ...] = field(repr=False)

    def matches(self, key: str) -> bool:
        """Whether any pattern matches the whole ``key``."""
        return any(regex.fullmatch(key) for regex in self.regexes)

    def matching(self, key: str) -> tuple[str, ...]:
        """The patterns (as written) that match the whole ``key``, in order."""
        pairs = zip(self.patterns, self.regexes, strict=True)
        return tuple(pattern for pattern, regex in pairs if regex.fullmatch(key))


def compile_globs(
    patterns: Iterable[str], *, platform: str = sys.platform, home: str | None = None
) -> GlobSet:
    """Compile ``patterns`` for matching folded keys on ``platform``.

    A ``~/`` pattern expands against ``home``; without one it can never match
    an absolute key, so the runtime always passes the hook process's home.

    Example::

        >>> compile_globs(["~/.ssh/**"], platform="linux", home="/h").matches("/h/.ssh/id")
        True
    """
    kept = tuple(patterns)
    regexes = tuple(re.compile(glob_to_regex(_prepared(p, platform, home))) for p in kept)
    return GlobSet(kept, regexes)


def glob_to_regex(pattern: str) -> str:
    """The ``re.fullmatch`` body for one glob (no folding, no ``~`` expansion).

    Example::

        >>> glob_to_regex(".env*")
        '(?:.*/)?\\\\.env[^/]*'
    """
    if pattern.endswith("/"):
        pattern += "**"
    pieces: list[str] = []
    index = 0
    while index < len(pattern):
        piece, index = _translate_at(pattern, index)
        pieces.append(piece)
    body = "".join(pieces)
    return body if "/" in pattern else _ANY_DIRS + body


def fold_key(text: str, platform: str) -> str:
    """``text`` as a match key: NFC + case-folded on darwin and win32, else unchanged.

    ``fnmatch`` does not fold case on darwin and ``realpath`` does not fold it
    either, while both platforms' default filesystems do; over-matching on a
    case-sensitive volume is the safe direction for guards.

    Example::

        >>> fold_key(".ENV", "darwin")
        '.env'
    """
    if platform not in FOLDING_PLATFORMS:
        return text
    import unicodedata  # only the folding platforms pay for it (§D.1)

    return unicodedata.normalize("NFC", text).casefold()


def _prepared(pattern: str, platform: str, home: str | None) -> str:
    if home is not None and pattern.startswith("~/"):
        pattern = home.rstrip("/") + pattern[1:]
    return fold_key(pattern, platform)


def _translate_at(pattern: str, index: int) -> tuple[str, int]:
    """The regex for the glob token at ``index`` and the index after it."""
    char = pattern[index]
    if char == "*":
        return _translate_stars(pattern, index)
    if char == "?":
        return "[^/]", index + 1
    if char == "[":
        return _translate_class(pattern, index)
    return re.escape(char), index + 1


def _translate_stars(pattern: str, index: int) -> tuple[str, int]:
    end = index
    while end < len(pattern) and pattern[end] == "*":
        end += 1
    if end - index == 1:
        return "[^/]*", end
    if end < len(pattern) and pattern[end] == "/":
        return _ANY_DIRS, end + 1
    return ".*", end


def _translate_class(pattern: str, index: int) -> tuple[str, int]:
    start = index + 1
    if start < len(pattern) and pattern[start] in "!^":
        start += 1
    if start < len(pattern) and pattern[start] == "]":
        start += 1
    end = pattern.find("]", start)
    if end < 0:
        return re.escape("["), index + 1  # an unclosed bracket is a literal
    inner = pattern[index + 1 : end]
    negate = inner[:1] in ("!", "^")
    body = "".join("\\" + c if c in _CLASS_SPECIAL else c for c in inner[negate:])
    return f"[{'^' if negate else ''}{body}]", end + 1
