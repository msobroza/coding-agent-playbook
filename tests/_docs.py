"""The user docs pages and a fence-aware heading scan, shared by the docs-consistency tests.

Since prU D55 the README is a short user README and its former sections live in the
``docs/`` pages of :data:`USER_DOC_PAGES`. The hooks, glossary, skill-roots and user
README pins all read those pages, so the list and its readers live here, once.
"""

from __future__ import annotations

import re
from typing import Final

from tests._catalog import REPO_ROOT

#: The pages that hold the README's former sections (prU D55), in reading order.
USER_DOC_PAGES: Final = (
    "docs/overview.md",
    "docs/setup.md",
    "docs/skills.md",
    "docs/hooks.md",
    "docs/checks.md",
)
#: A fence line (```` ``` ```` or ```` ```lang ````); group 1 is the language.
FENCE: Final = re.compile(r"^\s*```(\w*)\s*$")
_HEADING = re.compile(r"^(#{1,6}) ")


def user_docs() -> str:
    """Every page of :data:`USER_DOC_PAGES`, joined; each page opens with its own ``#`` title.

    Example: ``"## Status" in user_docs()``.
    """
    pages = (REPO_ROOT / page for page in USER_DOC_PAGES)
    return "\n".join(page.read_text(encoding="utf-8") for page in pages)


def headings(text: str) -> list[tuple[int, int, str]]:
    """``(offset, level, line)`` of every heading outside fenced code (``# x`` in a block is not one).

    Example: ``[line for _, level, line in headings(text) if level == 2]``.
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
