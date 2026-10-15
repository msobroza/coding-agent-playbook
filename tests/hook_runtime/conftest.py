"""Fixtures for the ``hook_runtime`` suite (specs/prK-lifecycle-hooks.md §D.9).

The runtime itself never spawns processes in these tests: every function under
test is pure over its arguments. Only the ``real_git`` fixture runs the real
``git`` binary, to prove that the git-free repo discovery agrees with git; it
skips when git is not on PATH and isolates git from the developer's machine
through the root ``hermetic_git_env`` fixture.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

GIT_TIMEOUT_S = 30


@pytest.fixture
def real_git(hermetic_git_env: None) -> Callable[..., str]:
    """Return ``run(*args, cwd=path) -> stdout`` for the real git, or skip without one.

    Example::

        def test_x(real_git, tmp_path):
            real_git("init", "-q", cwd=tmp_path)
    """
    if shutil.which("git") is None:
        pytest.skip("git not on PATH")

    def _run(*args: str, cwd: Path) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
        )
        return completed.stdout.strip()

    return _run
