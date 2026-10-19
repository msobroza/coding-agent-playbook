"""Tests for ``git_diff``: the lines a change touched, for ``diff_coverage`` (prK §F.1.1).

:func:`parse_unified_zero` is pure, so the hunk forms are table-tested on
hand-written diffs. :func:`changed_lines` runs against real repositories in
``tmp_path`` under ``hermetic_git_env``; its git runner is injected, so the
timeout case uses :class:`FakeGitRunner` instead of patching :mod:`subprocess`.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.grading.baseline_git import GitTimeoutError, SubprocessGitRunner
from coding_agent_playbook.grading.execution_metrics.git_diff import (
    changed_lines,
    parse_unified_zero,
)
from tests.fakes import FakeGitRunner

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

_TIMEOUT_S = 10.0


def _diff(*hunks: str, path: str = "pkg/mod.py") -> str:
    header = f"diff --git a/{path} b/{path}\nindex 1..2 100644\n--- a/{path}\n+++ b/{path}\n"
    return header + "".join(f"{hunk}\n+added\n" for hunk in hunks)


@pytest.mark.parametrize(
    ("hunk", "expected"),
    [
        ("@@ -4 +5 @@", {5}),  # +c: one line
        ("@@ -4,2 +5 @@ def f():", {5}),  # +c after a -a,b; the section heading is ignored
        ("@@ -3,2 +2,0 @@", set()),  # +c,0: a pure deletion adds nothing
        ("@@ -1,0 +2,3 @@", {2, 3, 4}),  # +c,d
    ],
    ids=["plus-c", "plus-c-heading", "plus-c-0", "plus-c-d"],
)
def test_hunk_forms_plus_c_c0_cd(hunk: str, expected: set[int]) -> None:
    changed = parse_unified_zero(_diff(hunk))

    assert changed == ({"pkg/mod.py": frozenset(expected)} if expected else {})


def test_parse_merges_hunks_and_files() -> None:
    text = _diff("@@ -1 +1 @@", "@@ -9,0 +10,2 @@") + _diff("@@ -0,0 +1,2 @@", path="new.py")

    assert parse_unified_zero(text) == {
        "pkg/mod.py": frozenset({1, 10, 11}),
        "new.py": frozenset({1, 2}),
    }


def test_parse_ignores_added_lines_that_look_like_headers() -> None:
    """An added ``++ x`` reads ``+++ x`` inside a hunk; it is content, not a file header."""
    text = _diff("@@ -1,0 +1,2 @@") + "+++ b/other.py\n"

    assert parse_unified_zero(text) == {"pkg/mod.py": frozenset({1, 2})}


def test_parse_unquotes_c_quoted_names_and_skips_deleted_files() -> None:
    quoted = (
        'diff --git "a/sp\\303\\251cial.py" "b/sp\\303\\251cial.py"\n'
        '--- "a/sp\\303\\251cial.py"\n'
        '+++ "b/sp\\303\\251cial.py"\n'
        "@@ -1 +1 @@\n-x\n+y\n"
    )
    deleted = "diff --git a/gone.py b/gone.py\n--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n"

    assert parse_unified_zero(quoted + deleted) == {"spécial.py": frozenset({1})}


@pytest.fixture
def repo(tmp_path: Path, real_git: Callable[..., str]) -> Path:
    """One commit holding ``pkg/mod.py`` (5 lines), ``gone.py`` and ``move_me.py`` (6 lines)."""
    real_git("init", "-q", cwd=tmp_path)
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("a = 1\nb = 2\nc = 3\nd = 4\ne = 5\n")
    (tmp_path / "gone.py").write_text("x = 1\ny = 2\n")
    (tmp_path / "move_me.py").write_text("".join(f"v{i} = {i}\n" for i in range(6)))
    (tmp_path / "notes.txt").write_text("not python\n")
    real_git("add", "-A", cwd=tmp_path)
    real_git("commit", "-q", "-m", "base", cwd=tmp_path)
    return tmp_path


def test_pure_deletion_adds_nothing(repo: Path) -> None:
    (repo / "pkg" / "mod.py").write_text("a = 1\nb = 2\ne = 5\n")
    (repo / "gone.py").unlink()

    assert changed_lines(repo, "HEAD", timeout_s=_TIMEOUT_S) == {}


def test_multi_file(repo: Path) -> None:
    (repo / "pkg" / "mod.py").write_text("a = 1\nB = 2\nc = 3\nd = 4\ne = 5\nf = 6\n")
    (repo / "gone.py").write_text("x = 1\ny = 2\nz = 3\n")
    (repo / "notes.txt").write_text("changed, but not python\n")

    assert changed_lines(repo, "HEAD", timeout_s=_TIMEOUT_S) == {
        "pkg/mod.py": frozenset({2, 6}),
        "gone.py": frozenset({3}),
    }


def test_rename_under_M_counts_only_changed_lines(repo: Path, real_git: Callable[..., str]) -> None:
    real_git("mv", "move_me.py", "pkg/moved.py", cwd=repo)
    source = (repo / "pkg" / "moved.py").read_text().replace("v5 = 5", "v5 = 50")
    (repo / "pkg" / "moved.py").write_text(source)
    real_git("add", "-A", cwd=repo)

    assert changed_lines(repo, "HEAD", timeout_s=_TIMEOUT_S) == {"pkg/moved.py": frozenset({6})}


def test_untracked_file_counts_all_lines(repo: Path) -> None:
    (repo / "pkg" / "fresh.py").write_text("one = 1\ntwo = 2\nthree = 3")  # no final newline
    (repo / "pkg" / "empty.py").write_text("")
    (repo / "scratch.txt").write_text("untracked, but not python\n")

    assert changed_lines(repo, "HEAD", timeout_s=_TIMEOUT_S) == {
        "pkg/fresh.py": frozenset({1, 2, 3})
    }


@dataclass
class _SpyRun:
    """Wraps the real ``subprocess.run`` and records each git argv and its timeout."""

    calls: list[tuple[list[str], float | None]] = field(default_factory=list)

    def __call__(self, args: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((list(args), kwargs.get("timeout")))
        return subprocess.run(args, **kwargs)


def test_git_argv_is_hardened_and_bounded(repo: Path) -> None:
    spy = _SpyRun()
    (repo / "pkg" / "mod.py").write_text("a = 1\n")

    changed_lines(repo, "HEAD", timeout_s=_TIMEOUT_S, git=SubprocessGitRunner(repo, 4.5, run=spy))

    diff_argv = spy.calls[0][0]
    for flag in ("--no-ext-diff", "--no-textconv", "--no-color", "-M", "--unified=0"):
        assert flag in diff_argv
    assert diff_argv[-3:] == ["HEAD", "--", "*.py"]
    assert [timeout for _, timeout in spy.calls] == [4.5, 4.5]


def test_timeout_raises_runtime_error(tmp_path: Path) -> None:
    def timing_out(args: Sequence[str]) -> bytes:
        raise GitTimeoutError(args[0], 2.5)

    with pytest.raises(RuntimeError, match=r"since 'origin/main'.*timed out after 2\.5s"):
        changed_lines(tmp_path, "origin/main", timeout_s=2.5, git=timing_out)


def test_option_shaped_base_is_refused_before_git_runs(tmp_path: Path) -> None:
    git = FakeGitRunner()

    with pytest.raises(RuntimeError, match=r"'--output=x': not a revision"):
        changed_lines(tmp_path, "--output=x", timeout_s=_TIMEOUT_S, git=git)
    assert git.calls == []


def test_git_failure_raises_runtime_error_naming_the_base(tmp_path: Path) -> None:
    git = FakeGitRunner(fail_on={"diff"})

    with pytest.raises(RuntimeError, match=r"since 'nope'.*fatal: diff failed"):
        changed_lines(tmp_path, "nope", timeout_s=_TIMEOUT_S, git=git)
