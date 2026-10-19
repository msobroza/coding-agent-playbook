"""Thin, injectable, read-only git interface for ``playbook sync`` (SPEC §12.2/§12.3).

``playbook sync`` asks git exactly two questions: which paths are still
*tracked* (a migration warning under ``[output] commit = false``, and the
leftover policy's "never delete a tracked file" rule), and which paths are
*staged* (for the ``--check-staged`` commit guard). Both live behind the
:class:`GitClient` protocol so commands take the client as a parameter and tests
inject a fake instead of patching :mod:`subprocess`.

The engine never mutates git state: no ``add``, ``rm``, or ``commit`` — it only
prints the command for the user to run. Every failure mode (git missing, not a
repository, timeout, non-zero exit) degrades to ``None`` = "unknown". A warning
skips silently on ``None``; a deletion decision treats it as "maybe tracked"
inside a git work tree (``sync/_leftovers.py``) — it fails closed.
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

#: Upper bound for one git call. Both queries are local index reads; anything
#: slower means a wedged repo (lock contention, network FS) — give up silently.
GIT_TIMEOUT_SECONDS = 10.0


class GitClient(Protocol):
    """The read-only git queries ``playbook sync`` needs. ``None`` = unknown."""

    def tracked_paths(
        self, repo_root: Path, paths: Sequence[str], *, ignore_case: bool = False
    ) -> list[str] | None:
        """Return the tracked paths matching ``paths`` (relative to ``repo_root``).

        ``ignore_case`` matches case-insensitively and returns the index's own
        spelling, which may differ from the query's; the caller confirms a match
        (by file identity) before trusting it.
        """
        ...

    def staged_paths(self, repo_root: Path) -> list[str] | None:
        """Return staged added/modified paths relative to ``repo_root`` (no deletions)."""
        ...


class SubprocessGitClient:
    """:class:`GitClient` backed by the ``git`` binary (arg-list, no shell).

    Example::

        >>> SubprocessGitClient().staged_paths(Path("."))  # doctest: +SKIP
        ['src/app.py']
    """

    def __init__(self, *, executable: str = "git", timeout: float = GIT_TIMEOUT_SECONDS) -> None:
        self._executable = executable
        self._timeout = timeout

    def tracked_paths(
        self, repo_root: Path, paths: Sequence[str], *, ignore_case: bool = False
    ) -> list[str] | None:
        """``git ls-files`` with literal pathspecs, so ``*``/``?`` in names never glob.

        Git pathspecs are case-sensitive even under ``core.ignorecase``, so on a
        case-insensitive filesystem an index entry ``Demo/x`` is invisible to the
        query ``demo/x`` — the same file. ``ignore_case`` uses the
        ``:(literal,icase)`` magic instead (``--literal-pathspecs`` would disable it).
        """
        if not paths:
            return []
        if ignore_case:
            specs = [f":(literal,icase){path}" for path in paths]
            return self._run_z(["ls-files", "-z", "--", *specs], repo_root)
        return self._run_z(["--literal-pathspecs", "ls-files", "-z", "--", *paths], repo_root)

    def staged_paths(self, repo_root: Path) -> list[str] | None:
        """Staged paths relative to ``repo_root`` (``--relative``), deletions excluded.

        ``--diff-filter=d`` drops staged deletions so ``git rm --cached <output>``
        (the documented migration) never trips the guard; ``--no-renames`` splits
        a rename into delete + add so the new name is still reported.
        """
        args = ["diff", "--cached", "--name-only", "-z", "--relative", "--no-renames"]
        return self._run_z([*args, "--diff-filter=d"], repo_root)

    def _run_z(self, args: list[str], cwd: Path) -> list[str] | None:
        """Run ``git <args>`` in ``cwd``; split NUL-delimited stdout, ``None`` on failure."""
        try:
            proc = subprocess.run(
                [self._executable, *args],
                cwd=cwd,
                capture_output=True,
                timeout=self._timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        return [os.fsdecode(raw) for raw in proc.stdout.split(b"\0") if raw]
