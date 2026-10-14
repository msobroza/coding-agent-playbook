"""Unit tests for spelling-proof file membership (``_file_identity.py``)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook._file_identity import FileSet, file_identity

if TYPE_CHECKING:
    import pytest


def test_file_identity_is_none_for_a_missing_path(tmp_path: Path) -> None:
    assert file_identity(tmp_path / "missing") is None


def test_file_set_holds_members_by_resolved_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.md").write_text("a")
    members = FileSet.of([tmp_path / "a.md", tmp_path / "not-yet-written.md"])
    monkeypatch.chdir(tmp_path)
    assert members.holds(tmp_path / "a.md")
    assert members.holds(Path("a.md"))  # relative spelling
    assert members.holds(tmp_path / "not-yet-written.md")  # absent: by path only
    assert not members.holds(tmp_path / "b.md")


def test_file_set_holds_another_name_of_the_same_file(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("a")
    os.link(tmp_path / "a.md", tmp_path / "alias.md")
    (tmp_path / "other.md").write_text("a")  # equal bytes, different file
    members = FileSet.of([tmp_path / "a.md"])
    assert members.holds(tmp_path / "alias.md")
    assert not members.holds(tmp_path / "other.md")


def test_file_set_add_extends_membership(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("a")
    members = FileSet()
    assert not members.holds(tmp_path / "a.md")
    members.add(tmp_path / "a.md")
    assert members.holds(tmp_path / "a.md")
