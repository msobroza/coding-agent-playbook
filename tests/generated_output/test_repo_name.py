"""The repo root and name every sync mode derives the same way (``generated_output/repo_name.py``).

Regression for #268: write mode named ``HARNESS.md`` after the typed
``--repo-root`` (``.`` gave ``harness``, ``x/..`` gave ``..``, a symlink its own
name) while ``sync --check`` used the resolved directory, so a fresh sync was
drift. Both now ask :func:`repo_dir_name`, which never depends on the spelling.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from coding_agent_playbook.generated_output.repo_name import (
    FALLBACK_REPO_NAME,
    canonical_root,
    repo_dir_name,
)

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")


def _case_insensitive(directory: Path) -> bool:
    """Whether ``directory``'s filesystem matches names regardless of case."""
    return Path(str(directory).upper()).exists() and Path(str(directory).lower()).exists()


@pytest.fixture
def probe(tmp_path: Path) -> Path:
    """A real directory named ``probe`` with an empty ``sub/`` inside."""
    root = tmp_path / "probe"
    (root / "sub").mkdir(parents=True)
    return root.resolve()


def test_dot_names_the_cwd(probe: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(probe)
    assert repo_dir_name(Path(".")) == "probe"
    assert repo_dir_name(Path("./")) == "probe"
    assert repo_dir_name(Path("")) == "probe"
    assert canonical_root(Path(".")) == probe


def test_dot_dot_names_the_parent(probe: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(probe / "sub")
    assert repo_dir_name(Path("..")) == "probe"
    assert repo_dir_name(probe / "sub" / "..") == "probe"
    assert canonical_root(Path("..")) == probe


def test_absolute_physical_root_is_unchanged(probe: Path) -> None:
    assert canonical_root(probe) == probe
    assert repo_dir_name(probe) == "probe"


@posix_only
def test_symlink_alias_names_its_target(probe: Path, tmp_path: Path) -> None:
    alias = tmp_path / "alias"
    alias.symlink_to(probe, target_is_directory=True)
    assert repo_dir_name(alias) == "probe"
    assert canonical_root(alias) == probe


@posix_only
def test_symlink_loop_does_not_raise(tmp_path: Path) -> None:
    """Python 3.12's ``Path.resolve()`` raises ``RuntimeError`` on a loop; this must not."""
    loop = tmp_path / "loop"
    loop.symlink_to(loop)
    assert repo_dir_name(loop) == "loop"


def test_case_variant_spelling_names_the_on_disk_case(probe: Path) -> None:
    if not _case_insensitive(probe):
        pytest.skip("case-sensitive filesystem: PROBE is another directory")
    typed = probe.parent / "PROBE"
    assert repo_dir_name(typed) == "probe"
    assert canonical_root(typed) == probe


def test_case_sensitive_sibling_keeps_its_own_name(tmp_path: Path) -> None:
    """Two real directories differing only in case each keep their own name."""
    (tmp_path / "Probe").mkdir()
    if _case_insensitive(tmp_path / "Probe"):
        pytest.skip("case-insensitive filesystem: one directory only")
    (tmp_path / "probe").mkdir()
    assert repo_dir_name(tmp_path / "Probe") == "Probe"
    assert repo_dir_name(tmp_path / "probe") == "probe"


def test_filesystem_root_falls_back(tmp_path: Path) -> None:
    root = Path(os.path.abspath(tmp_path)).anchor
    assert repo_dir_name(Path(root)) == FALLBACK_REPO_NAME == "harness"
    assert canonical_root(Path(root)) == Path(root)


def test_missing_root_keeps_its_spelling(tmp_path: Path) -> None:
    assert repo_dir_name(tmp_path / "gone") == "gone"


def test_unreadable_parent_keeps_the_resolved_name(
    probe: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A parent that cannot be listed (EACCES) leaves the resolved spelling as is."""

    def _refuse(path: object) -> list[str]:
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr("coding_agent_playbook.generated_output.repo_name.os.listdir", _refuse)
    assert repo_dir_name(probe) == "probe"
