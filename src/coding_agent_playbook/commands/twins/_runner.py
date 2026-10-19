"""The guard twins' shared run skeleton (specs/prT-package-layout.md B.9).

Every twin's ``run`` resolves ``--repo-root`` (the working directory by
default), runs its scan, prints what the scan reports and returns its exit
code. A scan that cannot check (no repository, a bad range, a malformed
policy) raises one of :data:`TWIN_ERRORS`: the twin prints one
``error: <message>`` line on stderr and exits 2, the contract CI and
pre-commit rely on (specs/prK-hook-pack.md §E.4). Opening git stays in each
scan, because a twin opens it only for the modes that need it.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.git import GitError

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["TWIN_ERRORS", "TwinOutcome", "run_twin"]

#: What a twin may raise that means "cannot check": exit 2, one ``error:`` line.
#: ``GitBaseError`` and the policy and ``--range`` errors are ``ValueError``s.
TWIN_ERRORS: Final[tuple[type[Exception], ...]] = (GitError, ValueError)


@dataclass(frozen=True, slots=True)
class TwinOutcome:
    """A twin's verdict: its exit code and the text it prints (nothing when empty).

    Example: ``TwinOutcome(1, "src/a.py:2: type-ignore: ...\\ngate-scan HEAD~1..HEAD: 1 blocking")``.
    """

    exit_code: int
    output: str


def run_twin(
    repo_root: str | None,
    scan: Callable[[Path], TwinOutcome],
    *,
    errors: tuple[type[Exception], ...] = TWIN_ERRORS,
) -> int:
    """Resolve ``repo_root`` (cwd by default), run ``scan``, print its output, return its code.

    An exception in ``errors`` prints ``error: <exc>`` on stderr and returns 2, the guard
    twins' shared contract (specs/prK-hook-pack.md §E.4).

    Example::

        >>> run_twin(None, lambda root: TwinOutcome(0, ""))
        0
    """
    root = Path(repo_root or ".").resolve()
    try:
        outcome = scan(root)
    except errors as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if outcome.output:
        print(outcome.output)
    return outcome.exit_code
