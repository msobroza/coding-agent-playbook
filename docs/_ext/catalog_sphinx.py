"""The Sphinx extension of the docs site: write the catalog pages, adapt the Markdown.

Thin on purpose: the page text comes from :mod:`catalog_pages`, the link map from
:mod:`repo_links` and the note boxes from :mod:`github_alerts`. The handlers take :class:`SphinxApp`, the slice of
``sphinx.application.Sphinx`` they use, so nothing here imports Sphinx and the
tests drive them with a fake app in the default ``.[dev]`` install.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Protocol

from catalog_pages import render_pages
from catalog_snapshot import load_snapshot
from github_alerts import alerts_to_admonitions
from repo_links import rewrite_repo_links

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from catalog_snapshot import CatalogSnapshot

#: Where the generated catalog pages go, under the source dir (git-ignored).
CATALOG_DIR: Final = Path("reference") / "catalog"

#: The branch the site links source files on.
SOURCE_BRANCH: Final = "main"


class SphinxConfig(Protocol):
    """The config values these handlers read (``conf.py``)."""

    playbook_repo_url: str


class SphinxApp(Protocol):
    """The slice of ``sphinx.application.Sphinx`` these handlers use."""

    @property
    def srcdir(self) -> str | Path: ...

    @property
    def config(self) -> SphinxConfig: ...

    def add_config_value(self, name: str, default: Any, rebuild: str, /, **kwargs: Any) -> None: ...

    def connect(self, event: str, callback: Callable[..., None], /) -> object: ...


def setup(app: SphinxApp) -> dict[str, Any]:
    """Register the config value and the event handlers (Sphinx's extension entry)."""
    app.add_config_value("playbook_repo_url", "", "env", types=[str])
    app.connect("builder-inited", write_catalog_pages)
    app.connect("source-read", adapt_page)
    app.connect("include-read", adapt_included_file)
    return {"version": "1", "parallel_read_safe": True, "parallel_write_safe": True}


def write_catalog_pages(app: SphinxApp) -> None:
    """``builder-inited`` handler: write the catalog pages before Sphinx reads sources."""
    srcdir = Path(app.srcdir)
    write_catalog(srcdir, app.config.playbook_repo_url, load_snapshot(srcdir.parent))


def write_catalog(srcdir: Path, repo_url: str, snapshot: CatalogSnapshot) -> None:
    """Render ``snapshot`` into ``<srcdir>/reference/catalog/``, linking sources under ``repo_url``.

    Example: ``write_catalog(Path("docs"), "https://github.com/o/r", load_snapshot(Path(".")))``.
    """
    tree_url = f"{repo_url}/tree/{SOURCE_BRANCH}/"
    sync_generated_dir(srcdir / CATALOG_DIR, render_pages(snapshot, source_tree_url=tree_url))


def adapt_page(app: SphinxApp, docname: str, source: list[str]) -> None:
    """``source-read`` handler: map repo-path links to site pages, alerts to note boxes."""
    blob_url = f"{app.config.playbook_repo_url}/blob/{SOURCE_BRANCH}/"
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
