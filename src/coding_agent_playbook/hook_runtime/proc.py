"""The runtime's only process seam (specs/prK-lifecycle-hooks.md §D.1, §D.9).

Every child process the hook runtime starts goes through :func:`run`, and
every ``PATH`` lookup through :func:`which`; tests swap both for ``FakeProc``
through ``RuntimeDeps.proc``. Three rules hold for every call:

- ``subprocess`` and ``shutil`` are imported inside the functions, so the hot
  path (an Edit, a non-git Bash call) never pays for them (D-6).
- A timeout is mandatory: a hook that waits forever blocks the harness, and
  OpenCode's ``Plugin.trigger`` has no timeout of its own (§D.4).
- A child never inherits the hook's stdin, which is the harness payload pipe:
  it gets ``input`` or an empty pipe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = ["ProcResult", "ProcTimeout", "SubprocessProc", "run", "which"]


@dataclass(frozen=True, slots=True)
class ProcResult:
    """What a finished child process returned; stdout and stderr stay bytes.

    Example::

        >>> ProcResult(argv=("git", "status"), returncode=0).ok
        True
    """

    argv: tuple[str, ...]
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""

    @property
    def ok(self) -> bool:
        """Whether the child exited 0."""
        return self.returncode == 0


class ProcTimeout(Exception):
    """A child outlived its timeout and was killed; the failure policy decides (§D.4).

    Only the program name is kept: the argv may carry repo data.

    Example::

        >>> str(ProcTimeout("git", 2.0))
        'git did not finish within 2.0 s'
    """

    def __init__(self, program: str, timeout: float) -> None:
        super().__init__(f"{program} did not finish within {timeout} s")
        self.program = program
        self.timeout = timeout


def run(
    argv: Sequence[str],
    *,
    timeout: float,
    env: Mapping[str, str] | None = None,
    input: bytes | None = None,
    cwd: str | None = None,
) -> ProcResult:
    """Run ``argv`` to completion within ``timeout`` seconds and capture its output.

    ``env`` replaces the child environment when given; ``input`` is written to
    its stdin, which is otherwise empty. A non-zero exit is returned,
    not raised; a timeout raises :class:`ProcTimeout`, and a missing program
    raises ``OSError``.

    Example::

        >>> run(["git", "--version"], timeout=2.0).ok  # doctest: +SKIP
        True
    """
    command = _checked_argv(argv)
    _check_timeout(timeout)
    import subprocess  # lazy: only the git and stage paths spawn (D-6)

    try:
        completed = subprocess.run(
            command,
            # Empty input still gives the child its own closed pipe: it reads
            # EOF instead of the harness payload this process was fed.
            input=b"" if input is None else input,
            capture_output=True,
            timeout=timeout,
            env=None if env is None else dict(env),
            cwd=cwd,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ProcTimeout(command[0], timeout) from None
    return ProcResult(tuple(command), completed.returncode, completed.stdout, completed.stderr)


def which(name: str, *, path: str | None = None) -> str | None:
    """The absolute path of program ``name`` on ``path`` (default ``$PATH``), or ``None``.

    Example::

        >>> which("definitely-not-a-program") is None
        True
    """
    import shutil  # lazy, like subprocess

    return shutil.which(name, path=path)


class SubprocessProc:
    """``ProcPort`` over the real :func:`run` and :func:`which`; ``RuntimeDeps``' default.

    Example::

        >>> SubprocessProc().which("definitely-not-a-program") is None
        True
    """

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float,
        env: Mapping[str, str] | None = None,
        input: bytes | None = None,
        cwd: str | None = None,
    ) -> ProcResult:
        """See :func:`run`."""
        return run(argv, timeout=timeout, env=env, input=input, cwd=cwd)

    def which(self, name: str, *, path: str | None = None) -> str | None:
        """See :func:`which`."""
        return which(name, path=path)


def _checked_argv(argv: Sequence[str]) -> list[str]:
    command = list(argv)
    if not command:
        raise ValueError("argv is empty; expected [program, *args]")
    return command


def _check_timeout(timeout: float) -> None:
    if not (math.isfinite(timeout) and timeout > 0):
        raise ValueError(f"timeout must be a positive, finite number of seconds; got {timeout!r}")
