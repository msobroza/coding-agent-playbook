"""A bounded child process that takes its whole process group with it (stdlib-only).

``subprocess.run(timeout=...)`` kills only its direct child on POSIX, so an agent
CLI's node workers and MCP servers, a judge CLI's children, a tool's helpers or a
test's own subprocess kept running for the rest of an ``eval --record`` run.
:func:`run_bounded` starts the child in a session (and process group) of its own
and kills the group when the run ends in a timeout or any other exception.

It lives in ``grading`` because that is the lowest layer both of its caller
packages may import: the grading kernel (``tool_runner``, ``baseline_git``,
``execution_metrics.project``) and ``evals`` above it. Callers reach it as
``bounded_subprocess.run_bounded(...)``, looked up at call time, so a test can
replace that one attribute for every caller.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
from typing import TYPE_CHECKING, Any, Literal, overload

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

__all__ = ["run_bounded"]


@overload
def run_bounded(
    argv: Sequence[str],
    *,
    timeout_s: float | None,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    input: str | None = None,
    text: Literal[True] = True,
    encoding: str | None = None,
    errors: str | None = None,
) -> subprocess.CompletedProcess[str]: ...


@overload
def run_bounded(
    argv: Sequence[str],
    *,
    timeout_s: float | None,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    input: bytes | None = None,
    text: Literal[False],
) -> subprocess.CompletedProcess[bytes]: ...


def run_bounded(
    argv: Sequence[str],
    *,
    timeout_s: float | None,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    input: str | bytes | None = None,
    text: bool = True,
    encoding: str | None = None,
    errors: str | None = None,
) -> subprocess.CompletedProcess[Any]:
    """Run ``argv`` with captured output, killing its process group on a timeout or any exception.

    Like ``subprocess.run(argv, capture_output=True, timeout=timeout_s, check=False)``:
    ``input`` feeds stdin (``None`` inherits it), ``text=False`` gives bytes, a
    missing program raises ``FileNotFoundError`` and a timeout re-raises
    ``TimeoutExpired`` with the partial ``stdout``/``stderr`` (bytes) it carries.
    Why the group kill on *any* exception: in its own session the child no longer
    gets the terminal's Ctrl-C, so a ``KeyboardInterrupt`` here must end it. It
    then waits for the child rather than draining its pipes, as ``subprocess.run``
    does on POSIX: a process that left the group can hold them open.

    Example::

        >>> run_bounded(["true"], timeout_s=5).returncode  # doctest: +SKIP
        0
    """
    posix = os.name == "posix"
    with subprocess.Popen(
        list(argv),
        cwd=cwd,
        env=env,
        stdin=None if input is None else subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
        encoding=encoding,
        errors=errors,
        start_new_session=posix,
    ) as proc:
        try:
            stdout, stderr = proc.communicate(input, timeout=timeout_s)
        except BaseException:
            _kill_group(proc, posix=posix)
            proc.wait()
            raise
    return subprocess.CompletedProcess(list(argv), proc.returncode, stdout, stderr)


def _kill_group(proc: subprocess.Popen[Any], *, posix: bool) -> None:
    """Kill ``proc``'s process group on POSIX, then ``proc`` itself.

    Why both: Windows has no ``killpg``, and on macOS ``killpg`` fails with
    ``EPERM`` once the group holds only the leader's zombie, while a process that
    left the group still holds the pipes. ``proc.kill`` is a no-op on a reaped child.
    """
    if posix:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
    proc.kill()
