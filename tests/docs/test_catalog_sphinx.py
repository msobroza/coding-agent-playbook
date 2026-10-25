"""The docs site's Sphinx handlers, driven through a fake app (docs/_ext/catalog_sphinx.py).

The module imports Sphinx for type hints only, so these run in the default
``.[dev]`` install; the docs CI job's strict build covers the real Sphinx.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from catalog_sphinx import (
    CATALOG_DIR,
    adapt_included_file,
    adapt_page,
    setup,
    sync_generated_dir,
    write_catalog,
    write_catalog_pages,
)
from tests.docs.catalog_samples import SAMPLE_SNAPSHOT

_REPO_URL = "https://example.test/o/r"


@dataclass
class FakeConfig:
    playbook_repo_url: str = _REPO_URL


@dataclass
class FakeSphinxApp:
    """The slice of ``sphinx.application.Sphinx`` the handlers touch."""

    srcdir: Path
    config: FakeConfig = field(default_factory=FakeConfig)
    config_values: list[tuple[Any, ...]] = field(default_factory=list)
    connected: list[tuple[str, Any]] = field(default_factory=list)

    def add_config_value(self, *args: Any, **kwargs: Any) -> None:
        self.config_values.append(args)

    def connect(self, event: str, handler: Any) -> None:
        self.connected.append((event, handler))


def test_setup_registers_the_repo_url_and_the_handlers(tmp_path: Path) -> None:
    app = FakeSphinxApp(srcdir=tmp_path)

    metadata = setup(app)

    assert [args[0] for args in app.config_values] == ["playbook_repo_url"]
    assert app.connected == [
        ("builder-inited", write_catalog_pages),
        ("source-read", adapt_page),
        ("include-read", adapt_included_file),
    ]
    assert metadata["parallel_read_safe"] is True


def test_write_catalog_renders_the_snapshot_under_the_source_dir(tmp_path: Path) -> None:
    # The real catalog takes seconds to load; test_catalog_snapshot.py covers it once.
    write_catalog(tmp_path / "docs", _REPO_URL, SAMPLE_SNAPSHOT)

    out = tmp_path / "docs" / CATALOG_DIR
    assert sorted(p.relative_to(out).as_posix() for p in out.rglob("*.md")) == [
        "hooks.md",
        "index.md",
        "plugins/demo_skills.md",
        "prompts.md",
        "skills/python-testing.md",
    ]
    assert f"{_REPO_URL}/tree/main/" in (out / "skills" / "python-testing.md").read_text()


def test_adapt_page_maps_links_and_alerts_in_place(tmp_path: Path) -> None:
    source = ["See [the spec](../SPEC.md).\n\n> [!NOTE]\n> Go [home](../README.md).\n"]

    adapt_page(FakeSphinxApp(srcdir=tmp_path), "overview", source)

    assert source == [
        f"See [the spec]({_REPO_URL}/blob/main/SPEC.md).\n\n:::{{note}}\nGo [home](index.md).\n:::\n"
    ]


def test_adapt_included_file_turns_alerts_into_note_boxes(tmp_path: Path) -> None:
    source = ["> [!WARNING]\n> Back up first.\n"]

    adapt_included_file(FakeSphinxApp(srcdir=tmp_path), Path("../CONTEXT.md"), "glossary", source)

    assert source == [":::{warning}\nBack up first.\n:::\n"]


def test_sync_generated_dir_keeps_unchanged_files_and_drops_stale_ones(tmp_path: Path) -> None:
    sync_generated_dir(tmp_path, {"index.md": "a\n", "skills/old.md": "x\n"})
    index = tmp_path / "index.md"
    os.utime(index, (1, 1))

    sync_generated_dir(tmp_path, {"index.md": "a\n", "skills/new.md": "y\n"})

    assert index.stat().st_mtime == 1
    assert not (tmp_path / "skills" / "old.md").exists()
    assert (tmp_path / "skills" / "new.md").read_text() == "y\n"
