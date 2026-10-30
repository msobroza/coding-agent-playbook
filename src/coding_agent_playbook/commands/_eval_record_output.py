"""What a ``--record`` stamps on and writes out: the checked-out commit and the metrics file.

Split from ``commands._eval_record`` so that module stays under 500 lines.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evals.run.git_env import without_repo_location

if TYPE_CHECKING:
    from pathlib import Path

#: Wall-clock bound (seconds) of the ``git rev-parse HEAD`` that names the commit.
_GIT_TIMEOUT: Final = 30.0


def head_commit(repo_root: Path) -> str | None:
    """The commit ``repo_root`` has checked out, or ``None`` outside a git checkout.

    Example::

        >>> head_commit(Path("."))  # doctest: +SKIP
        '26bddb8f...'
    """
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            env=without_repo_location(os.environ),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = completed.stdout.strip()
    return commit if completed.returncode == 0 and commit else None


def write_metrics(path: Path, metrics: dict[str, object]) -> None:
    """Write ``metrics`` to ``path`` as indented, key-sorted JSON.

    Example::

        >>> write_metrics(Path("m/opus.json"), metrics)  # doctest: +SKIP
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
