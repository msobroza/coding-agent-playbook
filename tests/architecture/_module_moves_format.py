"""R-FORMAT of the module-path rewrite script (specs/prT-package-layout.md 5.4.2).

After ``module_moves.apply`` rewrites files, ruff sorts their imports and formats
them. It always runs as ``python -m ruff`` with the running interpreter (the dev
venv), never a binary from PATH, and each run is bounded. Stdlib-only, like
``module_moves``.
"""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    Runner = Callable[..., subprocess.CompletedProcess[str]]

#: Generous: ruff takes about a second on this tree; a hung run must not block a move PR.
_RUFF_TIMEOUT_S: Final = 300


def run_ruff(repo_root: Path, paths: Sequence[Path], *, run: Runner = subprocess.run) -> None:
    """Sort the imports of the changed ``.py`` files, then format every changed file.

    ``ruff format`` also formats the Python code blocks of markdown, and a longer
    import line can need a reflow. Raises ``RuntimeError`` naming the command when
    ruff fails or times out. Example: ``run_ruff(repo, [repo / "tests/unit/test_toml.py"])``.
    """
    names = [path.relative_to(repo_root).as_posix() for path in paths]
    python = [name for name in names if name.endswith(".py")]
    if python:
        _ruff(run, repo_root, ["check", "--fix", "--exit-zero", "--select", "I", *python])
    if names:
        _ruff(run, repo_root, ["format", *names])


def _ruff(run: Runner, repo_root: Path, arguments: list[str]) -> None:
    command = [sys.executable, "-m", "ruff", *arguments]
    try:
        done = run(
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=_RUFF_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"{' '.join(command)} did not finish within {_RUFF_TIMEOUT_S} s"
        ) from error
    if done.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} exited {done.returncode}: {done.stderr.strip()}")
