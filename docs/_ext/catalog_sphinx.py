"""The Sphinx extension of the docs site: write the catalog pages, adapt the Markdown.

Thin on purpose: the page text comes from :mod:`catalog_pages`, the link map from
:mod:`repo_links`, the note boxes from :mod:`github_alerts` and the repository that
source links point to from :mod:`source_host`. The handlers take :class:`SphinxApp`,
the slice of ``sphinx.application.Sphinx`` they use, so nothing here imports Sphinx
and the tests drive them with a fake app in the default ``.[dev]`` install.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Protocol

from catalog_pages import render_pages
from catalog_snapshot import load_snapshot
from github_alerts import alerts_to_admonitions
from repo_links import rewrite_repo_links
from source_host import source_host_from_env

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from catalog_snapshot import CatalogSnapshot

#: Where the generated catalog pages go, under the source dir (git-ignored).
CATALOG_DIR: Final = Path("reference") / "catalog"

#: How long reading the checkout's ``origin`` remote may take before it is skipped.
GIT_TIMEOUT_S: Final = 10


class SphinxConfig(Protocol):
    """The config values these handlers read and fill."""

    playbook_tree_url: str
    playbook_blob_url: str
    html_context: dict[str, Any]


class SphinxApp(Protocol):
    """The slice of ``sphinx.application.Sphinx`` these handlers use."""

    @property
    def srcdir(self) -> str | Path: ...

    @property
    def config(self) -> SphinxConfig: ...

    def add_config_value(self, name: str, default: Any, rebuild: str, /, **kwargs: Any) -> None: ...

    def connect(self, event: str, callback: Callable[..., None], /) -> object: ...


def setup(app: SphinxApp) -> dict[str, Any]:
    """Register the config values and the event handlers (Sphinx's extension entry)."""
    app.add_config_value("playbook_tree_url", "", "env", types=[str])
    app.add_config_value("playbook_blob_url", "", "env", types=[str])
    app.connect("config-inited", resolve_source_host)
    app.connect("builder-inited", write_catalog_pages)
    app.connect("source-read", adapt_page)
    app.connect("include-read", adapt_included_file)
    return {"version": "1", "parallel_read_safe": True, "parallel_write_safe": True}


def resolve_source_host(
    app: SphinxApp,
    config: SphinxConfig,
    env: Mapping[str, str] = os.environ,
    read_origin: Callable[[Path], str | None] | None = None,
) -> None:
    """``config-inited`` handler: point source links at the repository this build runs in.

    A value ``conf.py`` sets is kept. The sidebar's repository link gets the
    repository's address and its forge's name ("Source on GitLab"). When no
    repository is known, the values stay empty and the site has no source links.
    """
    origin = (read_origin or git_origin_url)(Path(app.srcdir).parent)
    host = source_host_from_env(env, origin)
    config.playbook_tree_url = config.playbook_tree_url or (host.tree_url if host else "")
    config.playbook_blob_url = config.playbook_blob_url or (host.blob_url if host else "")
    config.html_context = {
        **config.html_context,
        "playbook_repo_url": host.repo_url if host else "",
        "playbook_forge": host.label if host else "",
    }


def git_origin_url(repo_root: Path) -> str | None:
    """The checkout's ``origin`` remote URL, or ``None`` without git, a repo or a remote."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    url = result.stdout.strip() if result.returncode == 0 else ""
    return url or None


def write_catalog_pages(app: SphinxApp) -> None:
    """``builder-inited`` handler: write the catalog pages before Sphinx reads sources."""
    srcdir = Path(app.srcdir)
    write_catalog(srcdir, app.config.playbook_tree_url, load_snapshot(srcdir.parent))


def write_catalog(srcdir: Path, tree_url: str, snapshot: CatalogSnapshot) -> None:
    """Render ``snapshot`` into ``<srcdir>/reference/catalog/``, linking sources under ``tree_url``.

    Example: ``write_catalog(Path("docs"), "https://github.com/o/r/tree/main/", snapshot)``.
    """
    sync_generated_dir(srcdir / CATALOG_DIR, render_pages(snapshot, source_tree_url=tree_url))


def adapt_page(app: SphinxApp, docname: str, source: list[str]) -> None:
    """``source-read`` handler: map repo-path links to site pages, alerts to note boxes."""
    blob_url = app.config.playbook_blob_url
    linked = rewrite_repo_links(source[0], docname=docname, blob_url=blob_url)
    source[0] = alerts_to_admonitions(linked)


def adapt_included_file(
    app: SphinxApp, relative_path: Path, parent_docname: str, source: list[str]
) -> None:
    """``include-read`` handler: alerts to note boxes in a file a page includes.

    MyST emits this event for its ``{include}`` directive, so ``README.md``,
    ``CONTEXT.md``, ``MIGRATION.md`` and ``catalog/README.md`` get note boxes too.
    """
    source[0] = alerts_to_admonitions(source[0])


def sync_generated_dir(root: Path, pages: Mapping[str, str]) -> None:
    """Make ``root`` hold exactly ``pages``: write changed files, delete stale ``.md`` files.

    An unchanged file keeps its mtime, so an incremental build does not re-read it.

    Example: ``sync_generated_dir(Path("docs/reference/catalog"), {"index.md": "# Catalog\\n"})``.
    """
    for relative, text in pages.items():
        path = root / relative
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    wanted = {root / relative for relative in pages}
    for stale in [p for p in root.rglob("*.md") if p not in wanted]:
        stale.unlink()
