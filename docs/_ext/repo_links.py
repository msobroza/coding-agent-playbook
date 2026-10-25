"""Rewrite links to repo files that the site shows under another page name, or not at all.

The Markdown under ``docs/`` links repo files by their path (``../README.md``) so it
reads on the forge. On the site those files are pages with other names (README is
the home page) or stay in the repository (``SPEC.md``), linked on the forge.
:func:`rewrite_repo_links` maps each such link; every other link is left for MyST
to resolve, and the strict build fails on one it cannot.
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

#: Repo files the site does not show: linked on the forge, or named as text when
#: the build knows no forge to link to.
REPOSITORY_ONLY: Final = ("SPEC.md",)

# A Markdown inline link: [text](path) or [text](path#anchor), no scheme, no spaces.
_LINK: Final = re.compile(
    r"\[(?P<text>[^\]]*)\]\((?P<path>(?![a-z][a-z0-9+.-]*:|#)[^)\s#]+)(?P<anchor>#[^)\s]*)?\)"
)


def rewrite_repo_links(text: str, *, docname: str, blob_url: str) -> str:
    """Point each link to a :data:`SITE_PAGES` or :data:`REPOSITORY_ONLY` file at its home.

    ``docname`` is the page's name under ``docs/`` (``"checks"``); ``blob_url``
    prefixes a repo path on the forge (``https://github.com/o/r/blob/main/``). When it
    is empty, a link to a :data:`REPOSITORY_ONLY` file becomes its text and the
    file's path.

    Example::

        >>> rewrite_repo_links("[home](../README.md)", docname="checks", blob_url="u/")
        '[home](index.md)'
    """

    def replace(match: re.Match[str]) -> str:
        repo_path = _repo_path(match["path"], docname)
        if repo_path in REPOSITORY_ONLY and not blob_url:
            return f"{match['text']} (`{repo_path}`)"
        target = _site_target(repo_path, docname, blob_url)
        if target is None:
            return match[0]
        return f"[{match['text']}]({target}{match['anchor'] or ''})"

    return _LINK.sub(replace, text)


def _repo_path(path: str, docname: str) -> str:
    """``path``, written relative to the page ``docname``, as a path from the repo root."""
    repo_path = posixpath.normpath(posixpath.join(posixpath.dirname(f"docs/{docname}"), path))
    return repo_path + "/" if path.endswith("/") else repo_path


def _site_target(repo_path: str, docname: str, blob_url: str) -> str | None:
    """The link target the site uses for ``repo_path``, or ``None`` to leave the link alone."""
    if repo_path in REPOSITORY_ONLY:
        return f"{blob_url}{repo_path}"
    site_doc = SITE_PAGES.get(repo_path)
    if site_doc is None:
        return None
    return posixpath.relpath(f"docs/{site_doc}.md", posixpath.dirname(f"docs/{docname}"))
