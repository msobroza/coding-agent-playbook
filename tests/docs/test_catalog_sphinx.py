"""The docs site's Sphinx handlers, driven through a fake app (docs/_ext/catalog_sphinx.py).

The module never imports Sphinx, so these run in the default ``.[dev]`` install;
the docs CI job's strict build covers the real Sphinx.
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
    git_origin_url,
    resolve_source_host,
    setup,
    sync_generated_dir,
    write_catalog,
    write_catalog_pages,
)
from tests.docs.catalog_samples import SAMPLE_SNAPSHOT

_REPO_URL = "https://example.test/o/r"


@dataclass
class FakeConfig:
    """The config values the handlers read and fill."""

    playbook_tree_url: str = f"{_REPO_URL}/tree/main/"
    playbook_blob_url: str = f"{_REPO_URL}/blob/main/"
    html_context: dict[str, Any] = field(default_factory=dict)


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


def test_setup_registers_the_link_prefixes_and_the_handlers(tmp_path: Path) -> None:
    app = FakeSphinxApp(srcdir=tmp_path)

    metadata = setup(app)

    assert [args[0] for args in app.config_values] == ["playbook_tree_url", "playbook_blob_url"]
    assert app.connected == [
        ("config-inited", resolve_source_host),
        ("builder-inited", write_catalog_pages),
        ("source-read", adapt_page),
        ("include-read", adapt_included_file),
    ]
    assert metadata["parallel_read_safe"] is True


def test_write_catalog_renders_the_snapshot_under_the_source_dir(tmp_path: Path) -> None:
    # The real catalog takes seconds to load; test_catalog_snapshot.py covers it once.
    write_catalog(tmp_path / "docs", f"{_REPO_URL}/tree/main/", SAMPLE_SNAPSHOT)

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


def test_resolve_source_host_fills_gitlab_links_from_gitlab_ci(tmp_path: Path) -> None:
    config = FakeConfig(playbook_tree_url="", playbook_blob_url="", html_context={"x": 1})
    env = {"GITLAB_CI": "true", "CI_PROJECT_URL": "https://gitlab.acme.test/tools/playbook"}

    resolve_source_host(FakeSphinxApp(srcdir=tmp_path), config, env, read_origin=_no_origin)

    assert config.playbook_tree_url == "https://gitlab.acme.test/tools/playbook/-/tree/main/"
    assert config.playbook_blob_url == "https://gitlab.acme.test/tools/playbook/-/blob/main/"
    assert config.html_context == {
        "x": 1,
        "playbook_repo_url": "https://gitlab.acme.test/tools/playbook",
        "playbook_forge": "GitLab",
    }


def test_resolve_source_host_reads_the_origin_of_the_checkout(tmp_path: Path) -> None:
    config = FakeConfig(playbook_tree_url="", playbook_blob_url="")
    seen: list[Path] = []

    def read_origin(repo_root: Path) -> str:
        seen.append(repo_root)
        return "git@gitlab.acme.test:tools/playbook.git"

    resolve_source_host(FakeSphinxApp(srcdir=tmp_path / "docs"), config, {}, read_origin)

    assert seen == [tmp_path]
    assert config.playbook_blob_url == "https://gitlab.acme.test/tools/playbook/-/blob/main/"


def test_without_a_known_repository_the_site_has_no_source_links(tmp_path: Path) -> None:
    config = FakeConfig(playbook_tree_url="", playbook_blob_url="")

    resolve_source_host(FakeSphinxApp(srcdir=tmp_path), config, {}, read_origin=_no_origin)

    assert (config.playbook_tree_url, config.playbook_blob_url) == ("", "")
    assert config.html_context == {"playbook_repo_url": "", "playbook_forge": ""}


def test_resolve_source_host_keeps_link_prefixes_conf_py_sets(tmp_path: Path) -> None:
    config = FakeConfig()

    resolve_source_host(FakeSphinxApp(srcdir=tmp_path), config, {}, read_origin=_no_origin)

    assert config.playbook_blob_url == f"{_REPO_URL}/blob/main/"


def test_git_origin_url_is_none_outside_a_repository(tmp_path: Path) -> None:
    assert git_origin_url(tmp_path) is None


def _no_origin(repo_root: Path) -> None:
    return None
