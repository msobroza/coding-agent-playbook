"""``scripts/release.py prepare`` from any worktree: a throwaway checkout of ``origin/main``.

The outer step fetches, adds a detached worktree at ``origin/main``, re-runs the
script there on that checkout's engine and always removes the worktree. git and
the inner run are the named fake ``FakeReleaseHost``.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from release import ReleaseError, main, prepare
from tests.release.release_fakes import BASE, FakeReleaseHost

if TYPE_CHECKING:
    from pathlib import Path


def _scratch(tmp_path: Path) -> Path:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    return scratch


def test_prepare_runs_the_checkout_step_on_a_detached_worktree_of_origin_main(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = FakeReleaseHost()
    scratch = _scratch(tmp_path)
    checkout = scratch / "checkout"

    code = prepare(tmp_path, version="9.9.9", runner=host, make_scratch=lambda: scratch)

    assert code == 0
    assert host.commands[0] == ["git", "fetch", "--tags", "origin"]
    assert host.ran("worktree", "add", "--detach", str(checkout), BASE)
    inner = next(c for c in host.commands if "prepare-checkout" in c)
    assert inner[1] == str(checkout / "scripts" / "release.py")
    assert inner[2:] == ["prepare-checkout", "--base", BASE, "--version", "9.9.9"]
    env = host.envs[host.commands.index(inner)]
    assert env is not None
    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(checkout / "src")
    assert host.ran("worktree", "remove", "--force", str(checkout))
    assert "inner out" in capsys.readouterr().out


def test_a_failed_checkout_step_still_removes_the_worktree(tmp_path: Path) -> None:
    host = FakeReleaseHost(inner_exit=1)
    scratch = _scratch(tmp_path)

    assert prepare(tmp_path, version=None, runner=host, make_scratch=lambda: scratch) == 1

    assert host.ran("worktree", "remove", "--force", str(scratch / "checkout"))
    assert not scratch.exists()


def test_a_failed_worktree_add_leaves_no_scratch_directory(tmp_path: Path) -> None:
    host = FakeReleaseHost(fail_on="worktree add")
    scratch = _scratch(tmp_path)

    with pytest.raises(ReleaseError, match="worktree add"):
        prepare(tmp_path, version=None, runner=host, make_scratch=lambda: scratch)

    assert not scratch.exists()
    assert not any("prepare-checkout" in c for c in host.commands)


def test_a_failed_fetch_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    host = FakeReleaseHost(fail_on="fetch")

    assert main(["prepare"], cwd=tmp_path, runner=host) == 1

    assert "`git fetch --tags origin` exited 1" in capsys.readouterr().err
    assert not host.ran("worktree", "add")
