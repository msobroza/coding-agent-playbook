"""``playbook ci``'s ``commit-convention`` row: cz over the branch's commits (specs/prK-hook-pack.md §F.4.3, §F.5).

A real git history (isolated through the hermetic git env) with backdated
``GIT_COMMITTER_DATE``s; ``FakeCiStepRunner`` records every ``cz`` argv, so
commitizen never runs. Only commits on or after ``[hooks.commit_convention]
cutover_date`` reach cz: one ``--rev-range`` for the whole range or a newest
linear tail, else ``--message`` per commit (a merge of main in the tail would
widen a range to main's own commits); the PR title is one more argv element.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.cli.parser import build_parser
from coding_agent_playbook.commands.twins import ci
from tests.conftest import _DEFAULT_CONFIG
from tests.fakes import FakeCiStepRunner
from tests.hook_runtime.fakes import FakeGit

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest


def _commit(real_git: Callable[..., str], root: Path, message: str) -> str:
    real_git("commit", "-q", "--allow-empty", "-m", message, cwd=root)
    return real_git("rev-parse", "HEAD", cwd=root)


_CZ = "/v/bin/cz"
_NEW = "2026-10-16T09:00:00+02:00"
_OLD = "2026-09-01T09:00:00+02:00"


def _history(
    tmp_path: Path,
    real_git: Callable[..., str],
    monkeypatch: pytest.MonkeyPatch,
    dates: tuple[str, ...],
    *,
    cutover: str | None,
) -> tuple[Path, list[str]]:
    """``main`` (one commit) and ``feat`` on top of it, one commit per committer date, oldest first."""
    root = Path(os.path.realpath(tmp_path)) / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text("[tool.commitizen]\nname = 'cz_conventional_commits'\n")
    if cutover is not None:
        table = f'\n[hooks.commit_convention]\ncutover_date = "{cutover}"\n'
        (root / ".coding-agent-playbook.toml").write_text(_DEFAULT_CONFIG + table, "utf-8")
    real_git("init", "-q", "-b", "main", cwd=root)
    real_git("commit", "-q", "--allow-empty", "-m", "base", cwd=root)
    real_git("checkout", "-q", "-b", "feat", cwd=root)
    shas = []
    for n, when in enumerate(dates):
        monkeypatch.setenv("GIT_COMMITTER_DATE", when)
        shas.append(_commit(real_git, root, f"msg {n}"))
    monkeypatch.delenv("GIT_COMMITTER_DATE")
    return root, shas


def _convention(
    root: Path,
    runner: FakeCiStepRunner,
    *,
    which: Callable[[str], str | None] = {"cz": _CZ}.get,
    env: dict[str, str] | None = None,
) -> int:
    args = build_parser().parse_args(
        ["ci", "--steps", "commit-convention", "--base", "main", "--repo-root", str(root)]
    )
    return ci.run(args, runner=runner, which=which, env=env or {})


def test_commit_convention_cutover_filter(
    tmp_path: Path, real_git: Callable[..., str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only post-cut-over commits reach cz: a contiguous newest tail is one rev-range."""
    root, shas = _history(tmp_path, real_git, monkeypatch, (_OLD, _NEW, _NEW), cutover="2026-10-15")
    runner = FakeCiStepRunner()

    assert _convention(root, runner) == 0

    assert runner.calls == [(_CZ, "check", "--rev-range", f"{shas[1]}^..HEAD")]


def test_commit_convention_after_merging_main_checks_only_the_branch_commits(
    tmp_path: Path, real_git: Callable[..., str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression (PR #32): main's post-cut-over squash commits, merged in, are not the branch's.

    ``<merge base>..HEAD`` is ``msg 2``, the merge and the legacy ``msg 0``; the old
    ``<oldest kept>^..HEAD`` range also reached main's ``Main squash (#27)``.
    """
    root, _ = _history(tmp_path, real_git, monkeypatch, (_OLD,), cutover="2026-10-15")
    monkeypatch.setenv("GIT_COMMITTER_DATE", _NEW)
    real_git("checkout", "-q", "main", cwd=root)
    _commit(real_git, root, "Main squash (#27)")
    real_git("checkout", "-q", "feat", cwd=root)
    real_git("merge", "-q", "--no-ff", "-m", "Merge branch 'main' into feat", "main", cwd=root)
    _commit(real_git, root, "msg 2")
    monkeypatch.delenv("GIT_COMMITTER_DATE")
    runner = FakeCiStepRunner()

    assert _convention(root, runner) == 0

    assert runner.calls == [
        (_CZ, "check", "--message", "Merge branch 'main' into feat\n"),
        (_CZ, "check", "--message", "msg 2\n"),
    ]


def test_commit_convention_unset_cutover_checks_the_whole_range(
    tmp_path: Path, real_git: Callable[..., str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = _history(tmp_path, real_git, monkeypatch, (_OLD, _NEW), cutover=None)
    base = real_git("rev-parse", "main", cwd=root)
    runner = FakeCiStepRunner()

    assert _convention(root, runner) == 0

    assert runner.calls == [(_CZ, "check", "--rev-range", f"{base}..HEAD")]


def test_commit_convention_non_contiguous_checks_each_message(
    tmp_path: Path, real_git: Callable[..., str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A commit amended after the cut-over (new committer date) under an older one."""
    root, _ = _history(tmp_path, real_git, monkeypatch, (_NEW, _OLD, _NEW), cutover="2026-10-15")
    runner = FakeCiStepRunner(cz_exits={"msg 2\n": 1})

    assert _convention(root, runner) == 1

    assert runner.calls == [
        (_CZ, "check", "--message", "msg 0\n"),
        (_CZ, "check", "--message", "msg 2\n"),
    ]


def test_commit_convention_pr_title_is_one_argv_element(
    tmp_path: Path, real_git: Callable[..., str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Squash merges: the title is checked too, never interpolated into a shell line."""
    root, _ = _history(tmp_path, real_git, monkeypatch, (_OLD,), cutover="2026-10-15")
    title = 'feat: x"; rm -rf / #'
    runner = FakeCiStepRunner()

    assert _convention(root, runner, env={"PLAYBOOK_PR_TITLE": title}) == 0

    assert runner.calls == [(_CZ, "check", "--message", title)]


def test_commit_convention_missing_cz_fails_the_step(
    tmp_path: Path,
    real_git: Callable[..., str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, _ = _history(tmp_path, real_git, monkeypatch, (_NEW,), cutover=None)
    runner = FakeCiStepRunner()

    assert _convention(root, runner, which=lambda name: None) == 1

    assert runner.calls == []
    out = capsys.readouterr().out
    assert "cz (commitizen) not found on PATH" in out
    assert "FAIL commit-convention (exit 1" in out


def test_commit_convention_skipped_without_commitizen(tmp_path: Path) -> None:
    runner = FakeCiStepRunner()
    git = FakeGit(default_branch_name="origin/main")
    args = build_parser().parse_args(
        ["ci", "--steps", "commit-convention", "--repo-root", str(tmp_path)]
    )

    assert ci.run(args, runner=runner, git=git) == 0

    assert (runner.calls, git.calls) == ([], [])


def test_commit_convention_bad_cutover_fails_the_step(
    tmp_path: Path, real_git: Callable[..., str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = _history(tmp_path, real_git, monkeypatch, (_NEW,), cutover="15/10/2026")
    runner = FakeCiStepRunner()

    assert _convention(root, runner) == 1
    assert runner.calls == []
