"""Regression tests for the git isolation in ``tests/conftest.py``.

The real-git tests must never reach the developer's repository or config:
not via ``GIT_DIR``/``GIT_INDEX_FILE`` that git exports to hooks in a linked
worktree, and not via git's default global excludes file. The
``hermetic_git_env`` fixture covers both per test; the session-wide strip covers
the tests that run git without it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from coding_agent_playbook.git_env import REPO_LOCATION_GIT_VARS
from tests._content import REPO_ROOT
from tests.conftest import apply_hermetic_git_env

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10, check=False
    )


def test_inherited_repo_locating_vars_cannot_redirect_git(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_home = tmp_path_factory.mktemp("xdg")
    apply_hermetic_git_env(monkeypatch, ceiling=tmp_path, config_home=config_home)
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    assert _git(decoy, "init", "-q").returncode == 0
    decoy_index = decoy / ".git" / "index"
    # What git exports to a hook running inside a linked worktree.
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(decoy_index))
    monkeypatch.setenv("GIT_WORK_TREE", str(decoy))

    apply_hermetic_git_env(monkeypatch, ceiling=tmp_path, config_home=config_home)
    work = tmp_path / "work"
    work.mkdir()
    (work / "AGENTS.md").write_text("x\n")
    assert _git(work, "init", "-q").returncode == 0
    assert _git(work, "add", "AGENTS.md").returncode == 0

    assert not decoy_index.exists()
    assert _git(work, "ls-files").stdout == "AGENTS.md\n"
    assert not {"GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"} & set(os.environ)


def test_default_global_excludes_file_is_ignored(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_config = tmp_path_factory.mktemp("user-xdg")
    (user_config / "git").mkdir()
    (user_config / "git" / "ignore").write_text("AGENTS.md\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(user_config))

    apply_hermetic_git_env(
        monkeypatch, ceiling=tmp_path.parent, config_home=tmp_path_factory.mktemp("xdg")
    )
    assert _git(tmp_path, "init", "-q").returncode == 0
    (tmp_path / "AGENTS.md").write_text("x\n")
    assert _git(tmp_path, "check-ignore", "-q", "AGENTS.md").returncode == 1  # not ignored


@pytest.mark.usefixtures("hermetic_git_env")
def test_fixture_config_home_is_empty_and_outside_tmp_path(tmp_path: Path) -> None:
    config_home = Path(os.environ["XDG_CONFIG_HOME"])
    assert config_home.is_dir()
    assert list(config_home.iterdir()) == []
    assert tmp_path not in config_home.parents
    assert os.environ["GIT_CONFIG_GLOBAL"] == os.devnull


def test_session_has_no_repo_location_git_vars() -> None:
    """Probe for the run below: nothing pins a git repository inside the session."""
    leaked = sorted(REPO_LOCATION_GIT_VARS.intersection(os.environ))
    assert leaked == []


def test_a_run_started_from_a_hook_drops_the_hook_git_vars(tmp_path: Path) -> None:
    """A run launched with what git exports to a linked-worktree hook strips it.

    The ``content-checks`` pre-commit hook runs tests that call ``materialize`` or
    ``git`` without ``hermetic_git_env``; they rely on this session-wide strip.
    """
    decoy = tmp_path / "decoy.git"
    env = {**os.environ, "GIT_DIR": str(decoy), "GIT_INDEX_FILE": str(decoy / "index")}
    probe = f"{__file__}::test_session_has_no_repo_location_git_vars"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-cov", "-p", "no:cacheprovider", probe],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
