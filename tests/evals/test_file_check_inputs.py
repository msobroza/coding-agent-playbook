"""Tests for :func:`freeze_file_inputs`: the file checks grade a copy made before the suite.

Regression: the file checks read the candidate tree after the scoring suite ran,
so a ``conftest.py`` could run edited code and then put the original bytes back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.checks.files import (
    FileExistsCheck,
    FileForbiddenCheck,
    FileUnchangedCheck,
    freeze_file_inputs,
)
from coding_agent_playbook.grading.compose import AllOf, Not

if TYPE_CHECKING:
    from pathlib import Path


def _tree(root: Path, files: dict[str, str]) -> Path:
    """Write ``files`` (relpath -> text) under ``root`` and return it."""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _frozen_files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def test_only_the_paths_the_checks_name_are_copied(tmp_path: Path) -> None:
    tree = _tree(tmp_path / "tree", {"a.py": "a", "pkg/b.py": "b", "other.py": "o"})
    checks = [AllOf(FileUnchangedCheck("a.py"), Not(FileExistsCheck("pkg/b.py")))]

    frozen = freeze_file_inputs(checks, tree, tmp_path / "frozen")

    assert _frozen_files(frozen) == ["a.py", "pkg/b.py"]
    assert (frozen / "pkg" / "b.py").read_text(encoding="utf-8") == "b"


def test_a_symlinked_file_is_frozen_by_content(tmp_path: Path) -> None:
    """A later change to the link's target does not reach the frozen copy."""
    target = _tree(tmp_path / "outside", {"real.py": "before"}) / "real.py"
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "link.py").symlink_to(target)

    frozen = freeze_file_inputs([FileUnchangedCheck("link.py")], tree, tmp_path / "frozen")
    target.write_text("after", encoding="utf-8")

    assert not (frozen / "link.py").is_symlink()
    assert (frozen / "link.py").read_text(encoding="utf-8") == "before"


def test_a_missing_path_stays_missing_and_a_dir_stays_a_non_file(tmp_path: Path) -> None:
    tree = _tree(tmp_path / "tree", {"build/out.txt": "x"})
    checks = [FileForbiddenCheck("gone.py"), FileForbiddenCheck("build")]

    frozen = freeze_file_inputs(checks, tree, tmp_path / "frozen")

    assert not (frozen / "gone.py").exists()
    assert (frozen / "build").is_dir()
    assert _frozen_files(frozen) == []


@pytest.mark.parametrize("path", ["../x.py", "a/../../x.py", "/etc/passwd"])
def test_a_path_outside_the_tree_is_refused(tmp_path: Path, path: str) -> None:
    with pytest.raises(ValueError, match=r"names '.*'; expected a relative path") as raised:
        freeze_file_inputs([FileExistsCheck(path)], tmp_path, tmp_path / "frozen")
    assert repr(path) in str(raised.value)
