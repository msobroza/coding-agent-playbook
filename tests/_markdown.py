"""Fence-aware markdown heading helpers for the docs-consistency tests.

The one home of "where does this section end": README.md and MIGRATION.md quote
generated markdown inside fenced blocks (``## Before you start``), and such a
line is no heading of the document, so every section split skips fences.
"""

from __future__ import annotations

import re

#: A fence line: three backticks, an optional info word, nothing else.
FENCE = re.compile(r"^\s*```(\w*)\s*$")
_HEADING = re.compile(r"^(#{1,6}) ")


def markdown_headings(text: str) -> list[tuple[int, int, str]]:
    """``(offset, level, line)`` of every heading outside fenced code (``# x`` in a block is not one).

    Example: ``markdown_headings("# A\\n```\\n## no\\n```\\n## B\\n")`` ->
    ``[(0, 1, "# A"), (18, 2, "## B")]``.
    """
    found: list[tuple[int, int, str]] = []
    fenced, offset = False, 0
    for line in text.splitlines(keepends=True):
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced and (match := _HEADING.match(line)):
            found.append((offset, len(match.group(1)), line.rstrip("\n")))
        offset += len(line)
    return found


def markdown_section(text: str, start: int) -> str:
    """The section whose heading starts at offset ``start``, up to the next heading of its level or above.

    Example: ``markdown_section("## A\\nx\\n### a\\n## B\\n", 0)`` -> ``"## A\\nx\\n### a\\n"``.
    """
    heads = markdown_headings(text)
    levels = [level for offset, level, _ in heads if offset == start]
    assert levels, f"offset {start} is no heading outside a code fence"
    end = next((at for at, lvl, _ in heads if at > start and lvl <= levels[0]), len(text))
    return text[start:end]
