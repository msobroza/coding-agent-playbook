"""Run real ``git`` in the CLI end-to-end tests, with one shared hang guard.

The e2e tests drive ``git`` over a synced repo (500+ files). The timeout only
catches a ``git`` that never returns; it is not a speed check, so it leaves
room for a loaded ``pytest -n`` run (``git add -A`` took over 10 s there).
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

#: Seconds a single ``git`` call may take before the test fails as hung.
GIT_HANG_GUARD_S = 60


def run_git(repo: Path, *args: str) -> str:
    """Run ``git *args`` in ``repo``, fail on a non-zero exit, return its stdout.

    Example: ``run_git(repo, "status", "--porcelain")`` -> ``"?? new.txt\\n"``.
    """
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        timeout=GIT_HANG_GUARD_S,
    )
    return proc.stdout
