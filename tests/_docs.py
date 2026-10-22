"""The user docs pages and their joined text, shared by the docs-consistency tests.

Since prU D55 the README is a short user README and its former sections live in the
``docs/`` pages of :data:`USER_DOC_PAGES`. The hooks, glossary, skill-roots and user
README pins all read those pages, so the list and its reader live here, once; the
fence-aware heading scan is :mod:`tests._markdown`.
"""

from __future__ import annotations

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


def user_docs() -> str:
    """Every page of :data:`USER_DOC_PAGES`, joined; each page opens with its own ``#`` title.

    Example: ``"## Status" in user_docs()``.
    """
    pages = (REPO_ROOT / page for page in USER_DOC_PAGES)
    return "\n".join(page.read_text(encoding="utf-8") for page in pages)
