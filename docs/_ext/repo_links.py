"""Rewrite links to repo files that the site shows under another page name, or not at all.

The Markdown under ``docs/`` links repo files by their path (``../README.md``) so it
reads on GitHub. On the site those files are pages with other names (README is
the home page) or stay on GitHub (``SPEC.md``). :func:`rewrite_repo_links` maps
each such link; every other link is left for MyST to resolve, and the strict
build fails on one it cannot.
"""

from __future__ import annotations

import posixpath
import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

#: Repo files the site shows as a page: repo path -> docname (under docs/).
SITE_PAGES: Final[Mapping[str, str]] = {
    "README.md": "index",
    "CONTEXT.md": "glossary",
    "MIGRATION.md": "upgrading",
    "catalog/README.md": "contributing",
    "docs/adr/": "adr/index",
}

#: Repo files the site leaves on GitHub: they are linked by URL instead.
GITHUB_ONLY: Final = ("SPEC.md",)

# A Markdown inline link's target: ](path) or ](path#anchor), no scheme, no spaces.
_LINK: Final = re.compile(r"\]\((?P<path>(?![a-z][a-z0-9+.-]*:|#)[^)\s#]+)(?P<anchor>#[^)\s]*)?\)")


def rewrite_repo_links(text: str, *, docname: str, blob_url: str) -> str:
    """Point each link to a :data:`SITE_PAGES` or :data:`GITHUB_ONLY` file at its site home.

    ``docname`` is the page's name under ``docs/`` (``"checks"``); ``blob_url``
    prefixes a repo path for GitHub (``https://github.com/o/r/blob/main/``).

    Example::

        >>> rewrite_repo_links("[home](../README.md)", docname="checks", blob_url="u/")
        '[home](index.md)'
    """

    def replace(match: re.Match[str]) -> str:
        target = _site_target(match["path"], docname, blob_url)
        return match[0] if target is None else f"]({target}{match['anchor'] or ''})"

    return _LINK.sub(replace, text)


def _site_target(path: str, docname: str, blob_url: str) -> str | None:
    """The link target the site uses for ``path``, or ``None`` to leave the link alone."""
    page_dir = posixpath.dirname(f"docs/{docname}")
    repo_path = posixpath.normpath(posixpath.join(page_dir, path))
    if path.endswith("/"):
        repo_path += "/"
    if repo_path in GITHUB_ONLY:
        return f"{blob_url}{repo_path}"
    site_doc = SITE_PAGES.get(repo_path)
    if site_doc is None:
        return None
    return posixpath.relpath(f"docs/{site_doc}.md", page_dir)
