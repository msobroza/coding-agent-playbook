"""Tests for ``tests/skill_lane.py``: the CI lane selector (ADR 0009).

:func:`lane_for` is pure, so the path sets are table-tested. :func:`main` takes
its git runner as a parameter, so the fail-to-full cases use :class:`FakeGit`
instead of patching :mod:`subprocess`. :func:`changed_paths` runs against a
real PR-style merge commit in ``tmp_path`` (``real_git`` under
``hermetic_git_env``), and one test runs the module the way the workflow does.

Not ``catalog``-marked: the selector is not skill content, so editing it selects
the full lane, which runs these tests.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests._catalog import REPO_ROOT
from tests.skill_lane import changed_paths, in_skill_lane, lane_for, main

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from tests.skill_lane import Lane

_SKILL_FILE = "catalog/core/skills/demo/SKILL.md"
_DIFF_ARGS = ("diff", "--name-only", "--no-renames", "HEAD^1", "HEAD")


@pytest.mark.parametrize(
    ("changed", "lane", "reason"),
    [
        (
            [_SKILL_FILE, "tests/core_skills/test_demo.py", "tests/core_skill_pins/test_pin.py"],
            "skill",
            "3 changed path(s), all skill content",
        ),
        (["catalog/core/ATTRIBUTIONS.md"], "skill", "1 changed path(s), all skill content"),
        (
            [_SKILL_FILE, "src/coding_agent_playbook/cli.py", "docs/x.md"],
            "full",
            "src/coding_agent_playbook/cli.py is outside the skill-lane paths",
        ),
        ([], "full", "no changed paths"),
        (
            ["catalog/core/rules/x.md"],
            "full",
            "catalog/core/rules/x.md is outside the skill-lane paths",
        ),
        (
            ["catalog/plugins/superpowers/skills/x/SKILL.md"],
            "full",
            "catalog/plugins/superpowers/skills/x/SKILL.md is outside the skill-lane paths",
        ),
        (
            ["tests/core_skills_extra/y.py"],
            "full",
            "tests/core_skills_extra/y.py is outside the skill-lane paths",
        ),
        (["tests/skill_lane.py"], "full", "tests/skill_lane.py is outside the skill-lane paths"),
    ],
    ids=[
        "all-skill",
        "attributions",
        "mixed",
        "empty",
        "core-rule",
        "plugin-skill",
        "prefix-lookalike",
        "selector-itself",
    ],
)
def test_lane_for(changed: list[str], lane: Lane, reason: str) -> None:
    assert lane_for(changed) == (lane, reason)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (_SKILL_FILE, True),
        ("catalog/core/skills", False),  # a file named like the directory
        ("catalog/core/ATTRIBUTIONS.md.orig", False),
        ('"catalog/core/skills/caf\\303\\251/SKILL.md"', False),  # git C-quotes non-ASCII
    ],
    ids=["skill-file", "bare-dir-name", "attributions-lookalike", "c-quoted"],
)
def test_in_skill_lane_matches_whole_prefixes_and_files_only(path: str, expected: bool) -> None:
    assert in_skill_lane(path) is expected


@dataclass
class FakeGit:
    """In-memory :data:`tests.skill_lane.GitRunner`: one canned ``git`` result.

    ``stdout`` and ``returncode`` shape the result; ``raises`` is raised instead
    (a timeout, a missing binary). ``calls`` records each ``(repo, args)``.
    """

    stdout: str = ""
    returncode: int = 0
    raises: Exception | None = None
    calls: list[tuple[Path, tuple[str, ...]]] = field(default_factory=list)

    def __call__(self, repo: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append((repo, tuple(args)))
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(["git", *args], self.returncode, self.stdout, "")


# The cases hold FakeGit factories, not instances: an instance built at import
# would carry its ``calls`` into a rerun of the same case.
@pytest.mark.parametrize(
    ("argv", "make_git", "reason"),
    [
        (
            ["--event", "push"],
            lambda: FakeGit(stdout=f"{_SKILL_FILE}\n"),
            "event push is not pull_request",
        ),
        (
            ["--event", "pull_request", "--force-full", "true"],
            lambda: FakeGit(stdout=f"{_SKILL_FILE}\n"),
            "the ci:full label forces it",
        ),
    ],
    ids=["push-event", "force-full"],
)
def test_full_lane_without_calling_git(
    argv: list[str],
    make_git: Callable[[], FakeGit],
    reason: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    git = make_git()

    assert main(argv, repo=tmp_path, run_git=git) == 0

    assert capsys.readouterr() == ("full\n", f"full lane: {reason}\n")
    assert git.calls == []


_NO_PATHS = "could not list the changed paths (git diff HEAD^1 HEAD failed)"


@pytest.mark.parametrize(
    ("make_git", "reason"),
    [
        (lambda: FakeGit(returncode=128), _NO_PATHS),
        (lambda: FakeGit(raises=subprocess.TimeoutExpired("git", 30)), _NO_PATHS),
        (lambda: FakeGit(raises=FileNotFoundError("git")), _NO_PATHS),
        (lambda: FakeGit(stdout=""), "no changed paths"),
        (
            lambda: FakeGit(stdout=f"{_SKILL_FILE}\nsrc/x.py\n"),
            "src/x.py is outside the skill-lane paths",
        ),
    ],
    ids=["git-fails", "git-times-out", "git-missing", "empty-diff", "mixed-diff"],
)
def test_pull_request_falls_to_the_full_lane(
    make_git: Callable[[], FakeGit],
    reason: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    git = make_git()

    assert main(["--event", "pull_request"], repo=tmp_path, run_git=git) == 0

    assert capsys.readouterr() == ("full\n", f"full lane: {reason}\n")
    assert git.calls == [(tmp_path, _DIFF_ARGS)]


def test_skill_only_pull_request_selects_the_skill_lane(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git = FakeGit(stdout=f"catalog/core/ATTRIBUTIONS.md\n{_SKILL_FILE}\n")

    argv = ["--event", "pull_request", "--force-full", "false"]

    assert main(argv, repo=tmp_path, run_git=git) == 0

    assert capsys.readouterr() == ("skill\n", "skill lane: 2 changed path(s), all skill content\n")
    assert git.calls == [(tmp_path, _DIFF_ARGS)]


@pytest.fixture
def git(real_git: Callable[..., str]) -> Callable[..., str]:
    """``real_git`` with an explicit identity on every call, for commits and merges."""

    def _run(*args: str, cwd: Path) -> str:
        identity = ("-c", "user.name=playbook-test", "-c", "user.email=test@example.invalid")
        return real_git(*identity, *args, cwd=cwd)

    return _run


@pytest.fixture
def repo(tmp_path: Path, git: Callable[..., str]) -> Path:
    """A ``main`` branch holding one skill file, checked out on a new ``topic`` branch."""
    git("init", "-q", "-b", "main", cwd=tmp_path)
    skill = tmp_path / _SKILL_FILE
    skill.parent.mkdir(parents=True)
    skill.write_text("v1\n", encoding="utf-8")
    git("add", "-A", cwd=tmp_path)
    git("commit", "-q", "-m", "base", cwd=tmp_path)
    git("switch", "-q", "-c", "topic", cwd=tmp_path)
    return tmp_path


def _merge_topic(git: Callable[..., str], repo: Path) -> None:
    """Commit the topic edit and merge it the way GitHub builds a PR merge commit.

    ``main`` moves on first, so the test proves the diff is against the first
    parent: the base's own change must not show up as a PR change.
    """
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "topic", cwd=repo)
    git("switch", "-q", "main", cwd=repo)
    (repo / "docs").mkdir()
    (repo / "docs" / "main_side.md").write_text("base moved on\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "main moves on", cwd=repo)
    git("merge", "--no-ff", "-q", "-m", "merge topic", "topic", cwd=repo)


def test_changed_paths_lists_only_the_pr_side_of_a_merge_commit(
    repo: Path, git: Callable[..., str]
) -> None:
    (repo / _SKILL_FILE).write_text("v2\n", encoding="utf-8")
    _merge_topic(git, repo)

    assert changed_paths(repo) == [_SKILL_FILE]


def test_a_rename_out_of_the_skills_lists_both_paths_and_selects_full(
    repo: Path, git: Callable[..., str]
) -> None:
    (repo / "src").mkdir()
    git("mv", _SKILL_FILE, "src/SKILL.md", cwd=repo)
    _merge_topic(git, repo)

    paths = changed_paths(repo) or []

    assert paths == [_SKILL_FILE, "src/SKILL.md"]
    assert lane_for(paths) == ("full", "src/SKILL.md is outside the skill-lane paths")


def test_the_module_entry_point_runs_the_way_ci_calls_it() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "tests.skill_lane", "--event", "push"],
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert (completed.returncode, completed.stdout) == (0, "full\n")
    assert completed.stderr == "full lane: event push is not pull_request\n"
