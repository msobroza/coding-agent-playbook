"""Tests for the Adapter ABC (PR 1 + PR 6 cleanup refactor)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.renderer import SENTINEL
from coding_agent_playbook.types import Prompt, Skill

if TYPE_CHECKING:
    from collections.abc import Iterable


class _DummyAdapter(Adapter):
    name = "dummy"

    def __init__(self) -> None:
        self.written_prompts: list[object] = []

    def write_rule(self, rule, repo_root):
        return []

    def write_prompt(self, prompt, repo_root):
        self.written_prompts.append(prompt)
        return [repo_root / f"{prompt}.md"]


class _ScannedAdapter(_DummyAdapter):
    """Subclass that publishes one output directory for cleanup scanning."""

    name = "scanned"

    def __init__(self, output_dir: Path) -> None:
        super().__init__()
        self._output_dir = output_dir

    def _output_directories(self, repo_root: Path) -> Iterable[Path]:
        return [self._output_dir]


def test_adapter_abc_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Adapter()  # type: ignore[abstract]


def test_concrete_subclass_can_be_instantiated():
    assert isinstance(_DummyAdapter(), Adapter)


def test_finalize_defaults_to_no_output():
    assert _DummyAdapter().finalize(Path(".")) == []


def test_write_skill_default_degrades_to_write_prompt(tmp_path):
    """The ABC's default write_skill calls Skill.to_prompt() and forwards the
    resulting Prompt to the adapter's write_prompt. _DummyAdapter records the
    prompt it received, so the test asserts on that."""
    skill = Skill(
        frontmatter={
            "id": "demo",
            "name": "Demo",
            "description": "A demo",
            "slash": "demo",
        },
        body="body\n",
        scripts_dir=None,
        references_dir=None,
        source_package="pkg",
    )
    adapter = _DummyAdapter()
    adapter.write_skill(skill, tmp_path)
    assert len(adapter.written_prompts) == 1
    # The forwarded artifact is the Prompt returned by Skill.to_prompt().
    forwarded = adapter.written_prompts[0]
    assert isinstance(forwarded, Prompt)
    assert forwarded.frontmatter.id == "demo"
    assert forwarded.body == "body\n"


def test_default_output_directories_is_empty():
    """ABC default returns no directories; subclasses opt in to scanning."""
    assert list(_DummyAdapter()._output_directories(Path("."))) == []


def test_default_cleanup_no_directories_returns_empty(tmp_path):
    """An adapter that does not override _output_directories cleans nothing."""
    assert _DummyAdapter().cleanup_stale(set(), tmp_path) == []


def test_default_cleanup_skips_missing_output_directory(tmp_path):
    """If the configured output dir does not exist, scan is a no-op."""
    missing = tmp_path / "never" / "created"
    adapter = _ScannedAdapter(missing)
    assert adapter.cleanup_stale(set(), tmp_path) == []


def test_default_cleanup_removes_stale_sentinel_file(tmp_path):
    """A sentinel-tagged file not in written_paths is deleted and returned."""
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    stale = output_dir / "stale.md"
    stale.write_text(f"<!-- {SENTINEL} -->\nbody\n", encoding="utf-8")
    adapter = _ScannedAdapter(output_dir)
    deleted = adapter.cleanup_stale(set(), tmp_path)
    assert deleted == [stale]
    assert not stale.exists()


def test_default_cleanup_preserves_written_paths(tmp_path):
    """A sentinel-tagged file IS preserved when its resolved path is in written_paths."""
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    current = output_dir / "current.md"
    current.write_text(f"<!-- {SENTINEL} -->\nbody\n", encoding="utf-8")
    adapter = _ScannedAdapter(output_dir)
    deleted = adapter.cleanup_stale({current.resolve()}, tmp_path)
    assert deleted == []
    assert current.exists()


def test_default_cleanup_preserves_user_authored_file(tmp_path):
    """Files without the sentinel are never deleted, even if not in written_paths."""
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    user_file = output_dir / "user.md"
    user_file.write_text("# Hand-written, never touch this\n", encoding="utf-8")
    adapter = _ScannedAdapter(output_dir)
    deleted = adapter.cleanup_stale(set(), tmp_path)
    assert deleted == []
    assert user_file.exists()


def test_default_cleanup_tolerates_binary_file(tmp_path):
    """Non-UTF-8 files in the scan dir don't crash the scanner."""
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    binary = output_dir / "image.bin"
    binary.write_bytes(b"\xff\xfe\x00\x00binary garbage")
    adapter = _ScannedAdapter(output_dir)
    deleted = adapter.cleanup_stale(set(), tmp_path)
    assert deleted == []
    assert binary.exists()


def test_default_cleanup_recursively_scans_subdirectories(tmp_path):
    """Stale sentinel files in nested subdirs are also removed."""
    output_dir = tmp_path / "out"
    nested = output_dir / "sub"
    nested.mkdir(parents=True)
    stale = nested / "deep.md"
    stale.write_text(f"<!-- {SENTINEL} -->\nbody\n", encoding="utf-8")
    adapter = _ScannedAdapter(output_dir)
    deleted = adapter.cleanup_stale(set(), tmp_path)
    assert deleted == [stale]
    assert not stale.exists()


def test_default_cleanup_never_deletes_a_written_file_under_another_name(tmp_path):
    """A case-only rename on a case-insensitive FS leaves the old spelling naming the
    file just written; a hard link reproduces that aliasing on every filesystem."""
    out = tmp_path / "out"
    out.mkdir()
    written = out / "demo.md"
    written.write_text(f"<!-- {SENTINEL} -->\nfresh\n", encoding="utf-8")
    os.link(written, out / "Demo-alias.md")
    adapter = _ScannedAdapter(out)

    assert adapter.cleanup_stale({written.resolve()}, tmp_path) == []
    assert written.read_text(encoding="utf-8").endswith("fresh\n")
