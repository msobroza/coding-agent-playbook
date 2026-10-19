"""Output caps and sanitization for everything the runtime shows (specs/prK-lifecycle-hooks.md §D.3.4).

Every model- or user-facing string passes through one of these before a
renderer sees it: reasons and notes through ``clamp_lines``, single fields
through ``clip``, and any repo-derived value (a path, a branch, a commit
subject) through ``quote_data``, the only way such data enters model-facing
text. Control characters never survive, so a hostile file name or an external
handler's output cannot inject terminal escapes into a user notice.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

__all__ = ["ELLIPSIS", "LineCap", "OutputCaps", "clamp_lines", "clean_text", "clip", "quote_data"]

#: Marks a cut; one character, so it fits inside every limit it is counted against.
ELLIPSIS: Final = "…"

# C0 controls except "\n", plus DEL: tabs and carriage returns become spaces too,
# so a line is always exactly what it looks like.
_CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class LineCap:
    """A line budget: at most ``max_lines`` lines of ``line_chars``, ``max_chars`` in all.

    ``max_chars`` counts the joining newlines; ``line_chars`` may not exceed
    it, so the first line always fits. Example: ``LineCap(4, 600, 160)`` is the
    deny/ask reason budget.
    """

    max_lines: int
    max_chars: int
    line_chars: int

    def __post_init__(self) -> None:
        if not 0 < self.line_chars <= self.max_chars or self.max_lines < 1:
            raise ValueError(
                f"LineCap needs max_lines >= 1 and 0 < line_chars <= max_chars, got "
                f"max_lines={self.max_lines}, max_chars={self.max_chars}, "
                f"line_chars={self.line_chars}"
            )


class OutputCaps:
    """The §D.3.4 caps, one name per channel.

    ``CONTEXT_ITEMS_PER_HOOK`` bounds what one hook contributes to an event's
    advisory context (the "5 items from project config" of §D.3.4, typically
    one project linter's findings) and ``CONTEXT_ITEMS_PER_EVENT`` what all
    hooks contribute together. ``FIELD_CHARS`` keeps every rendered field well
    under Claude's 10,000-character overflow-to-file threshold.

    Example: ``OutputCaps.REASON.max_lines == 4``.
    """

    REASON: Final = LineCap(max_lines=4, max_chars=600, line_chars=160)
    USER_NOTES: Final = LineCap(max_lines=6, max_chars=800, line_chars=800)
    STOP_REASON: Final = LineCap(max_lines=40, max_chars=4_000, line_chars=4_000)
    CONTEXT_ITEMS_PER_HOOK: Final = 5
    CONTEXT_ITEMS_PER_EVENT: Final = 8
    SESSION_START_CONTEXT_CHARS: Final = 600
    FIELD_CHARS: Final = 4_000
    QUOTE_CHARS: Final = 200


def clean_text(text: str) -> str:
    """``text`` with every control character except ``\\n`` replaced by a space.

    Example::

        >>> clean_text("a\\x1b[2Jb\\tc")
        'a [2Jb c'
    """
    return _CONTROL.sub(" ", text)


def clip(text: str, limit: int) -> str:
    """``text`` cut to ``limit`` characters, the last one an ellipsis when it was cut.

    Example::

        >>> clip("abcdef", 4)
        'abc…'
    """
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)] + ELLIPSIS if limit > 0 else ""


def clamp_lines(
    lines: Iterable[str], cap: LineCap, *, summary: Callable[[int], str] | None = None
) -> tuple[str, ...]:
    """The non-blank, cleaned lines of ``lines`` that fit ``cap``, in order.

    Each element may itself hold several lines. Every line is stripped of
    trailing whitespace and clipped to ``cap.line_chars``. When lines had to be
    dropped and ``summary`` is given, the last line kept is replaced by
    ``summary(hidden)``, ``hidden`` counting every line not shown.

    Example::

        >>> clamp_lines(["a", "", "b\\nc"], OutputCaps.REASON)
        ('a', 'b', 'c')
    """
    cleaned = [clip(line, cap.line_chars) for line in _split(lines)]
    kept = _fit(cleaned, cap)
    if summary is None or len(kept) == len(cleaned):
        return tuple(kept)
    head = kept[: cap.max_lines - 1]
    while True:
        marker = clip(summary(len(cleaned) - len(head)), cap.line_chars)
        if not head or _joined_len([*head, marker]) <= cap.max_chars:
            return (*head, marker)
        head.pop()


def quote_data(value: str, limit: int = OutputCaps.QUOTE_CHARS) -> str:
    """``value`` as a quoted, ASCII-only JSON string literal of at most ``limit`` characters.

    Newlines, control characters and non-ASCII text are escaped, so repo data
    can never pose as an instruction line in model-facing text.

    Example::

        >>> quote_data("a\\nb")
        '"a\\\\nb"'
    """
    return json.dumps(value[:limit], ensure_ascii=True)


def _split(lines: Iterable[str]) -> list[str]:
    """Every non-blank line of ``lines``, cleaned and right-stripped."""
    return [
        line.rstrip() for text in lines for line in clean_text(text).splitlines() if line.strip()
    ]


def _fit(lines: list[str], cap: LineCap) -> list[str]:
    """The longest prefix of ``lines`` within the line count and character budget."""
    kept: list[str] = []
    for line in lines:
        if len(kept) == cap.max_lines or _joined_len([*kept, line]) > cap.max_chars:
            break
        kept.append(line)
    return kept


def _joined_len(lines: list[str]) -> int:
    """The length of ``"\\n".join(lines)``, without building it."""
    return sum(map(len, lines)) + max(len(lines) - 1, 0)
