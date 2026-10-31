"""A bounded child process that takes its whole process group with it (stdlib-only).

``subprocess.run(timeout=...)`` kills only its direct child on POSIX, so an agent
CLI's node workers and MCP servers, a judge CLI's children, a tool's helpers or a
test's own subprocess kept running for the rest of an ``eval --record`` run.
:func:`run_bounded` starts the child in a session (and process group) of its own
and ends the group when the run ends in a timeout or any other exception: SIGTERM
first, then SIGKILL once the leader exits or :data:`_TERM_GRACE_S` ends.

In its own session the child no longer gets the signals sent to its parent's
group (a terminal's Ctrl-C or hangup, a supervisor's ``kill -TERM -<pgid>``), so
:func:`forward_signals_to_bounded_children` installs a handler that forwards
SIGINT, SIGTERM and SIGHUP to every live bounded group, then acts as the process
did before; after a SIGTERM or SIGHUP it SIGKILLs the groups still led by a live
process before it dies. The CLI entry point installs it from the main thread,
which covers the children of worker threads. A bounded child has no controlling terminal: an
inherited TTY stdin stays readable, but ``/dev/tty`` and job control are
unavailable, so a CLI that prompts on the terminal fails fast instead of waiting.

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
import threading
import time
from typing import TYPE_CHECKING, Any, Final, Literal, overload

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping, Sequence
    from pathlib import Path
    from types import FrameType

__all__ = ["forward_signals_to_bounded_children", "run_bounded"]

#: Read at call time, not import time, so a test can take the Windows path.
_POSIX = os.name == "posix"

#: Why a grace before the SIGKILL: a nested playbook process (the comparison
#: run's ``eval`` child) needs the moment to forward the SIGTERM to its own
#: groups (the agent CLI, the judge, the scoring suite); SIGKILL gives it none.
_TERM_GRACE_S: Final = 5.0

#: Why shorter: a nested bounded child (that ``eval`` child) is SIGKILLed by its
#: parent :data:`_TERM_GRACE_S` after the SIGTERM, so its own escalation (forward
#: the SIGTERM, wait, SIGKILL) must end strictly earlier, or a CLI under it that
#: ignores SIGTERM outlives them both.
_NESTED_TERM_GRACE_S: Final = _TERM_GRACE_S / 2

#: How long an ending sleeps between two checks of the leaders it signalled.
_LEADER_POLL_S: Final = 0.05

#: The pids of the live bounded children; each leads its own process group.
#: Why no lock: the signal handler runs in the main thread between bytecodes, so
#: a lock the main thread already held would deadlock it, while ``set.add``,
#: ``discard`` and ``copy`` are each atomic under the GIL.
_live_bounded_groups: set[int] = set()


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
    """Run ``argv`` with captured output, ending its process group on a timeout or any exception.

    Like ``subprocess.run(argv, capture_output=True, timeout=timeout_s, check=False)``:
    ``input`` feeds stdin (``None`` inherits it), ``text=False`` gives bytes, a
    missing program raises ``FileNotFoundError`` and a timeout re-raises
    ``TimeoutExpired`` with the partial ``stdout``/``stderr`` (bytes) it carries.

    On POSIX the child runs in a session of its own, without a controlling
    terminal (an inherited TTY stdin stays readable; ``/dev/tty`` and job control
    do not work). The signals its parent gets reach it through
    :func:`forward_signals_to_bounded_children`, installed here when called from
    the main thread. On a timeout or any exception (a ``KeyboardInterrupt``
    included) the group gets SIGTERM, then SIGKILL once the child exits or
    :data:`_TERM_GRACE_S` ends, so a nested run can end its own groups first. It
    then waits for the child rather than draining its pipes, as ``subprocess.run``
    does on POSIX: a process that left the group can hold them open. On Windows a
    timeout reads the output after the kill, as ``subprocess.run`` does there.

    One window is left: a signal landing inside ``Popen`` itself, after the fork
    and before the pid is known, leaves the child running (an accepted risk of
    microseconds).

    Example::

        >>> run_bounded(["true"], timeout_s=5).returncode  # doctest: +SKIP
        0
    """
    forward_signals_to_bounded_children()
    posix = _POSIX
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
            _live_bounded_groups.add(proc.pid)
            stdout, stderr = proc.communicate(input, timeout=timeout_s)
        except BaseException as exc:
            _end_bounded_child(proc, exc, posix=posix)
            raise
        finally:
            _live_bounded_groups.discard(proc.pid)
    return subprocess.CompletedProcess(list(argv), proc.returncode, stdout, stderr)


def forward_signals_to_bounded_children() -> None:
    """Forward SIGINT, SIGTERM and SIGHUP to every live bounded child's group (POSIX).

    Installs the handler only from the main thread (``signal.signal`` raises
    elsewhere) and only over a default disposition: a program's own handler and
    an inherited ``SIG_IGN`` (``nohup``) stay. Installing twice is a no-op. Call
    it early in an entry point whose worker threads run :func:`run_bounded`.

    Example::

        >>> forward_signals_to_bounded_children()  # doctest: +SKIP
    """
    if not _POSIX or threading.current_thread() is not threading.main_thread():
        return
    for signum, default in _default_dispositions().items():
        if signal.getsignal(signum) == default:
            signal.signal(signum, _forward_to_bounded_groups)


def _default_dispositions() -> dict[signal.Signals, object]:
    """The disposition a fresh Python process has for each forwarded signal."""
    return {
        signal.SIGINT: signal.default_int_handler,
        signal.SIGTERM: signal.SIG_DFL,
        signal.SIGHUP: signal.SIG_DFL,
    }


def _forward_to_bounded_groups(signum: int, frame: FrameType | None) -> None:
    """Send ``signum`` to every live bounded group, then do what the default did.

    SIGINT raises ``KeyboardInterrupt``, whose unwinding ends the groups. SIGTERM
    and SIGHUP cannot unwind, so the groups whose leader outlives the grace
    (:func:`_own_term_grace_s`) get SIGKILL here; then ``SIG_DFL`` is restored and
    the signal re-sent, so the process still dies by it.
    """
    if signum == signal.SIGINT:
        for pgid in _live_bounded_groups.copy():
            _signal_group(pgid, signum)
        signal.default_int_handler(signum, frame)
        return
    _end_groups(_live_bounded_groups.copy(), signum, _own_term_grace_s())
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def _own_term_grace_s() -> float:
    """How long this process lets its groups end after a SIGTERM before the SIGKILL.

    Why the session test: a bounded child leads a session of its own, and the
    run above it SIGKILLs it :data:`_TERM_GRACE_S` after the SIGTERM; a terminal's
    job does not lead its session and has no such deadline. A top-level process
    that does (``setsid``, a container's init) takes the shorter grace too.
    """
    return _NESTED_TERM_GRACE_S if os.getsid(0) == os.getpid() else _TERM_GRACE_S


def _forget_parent_groups() -> None:
    """Empty the live set in a forked child: its parent's groups are not its to signal.

    Why: a forked worker (``multiprocessing``'s fork context) inherits the handler
    and the set, so terminating it ended every run its parent had going.
    """
    _live_bounded_groups.clear()


if _POSIX:
    os.register_at_fork(after_in_child=_forget_parent_groups)


def _end_bounded_child(proc: subprocess.Popen[Any], exc: BaseException, *, posix: bool) -> None:
    """End ``proc`` (and on POSIX its group) after ``exc``, then reap it.

    Why ``proc.kill`` after the group kill: Windows has no ``killpg``, and on macOS
    ``killpg`` fails with ``EPERM`` once the group holds only the leader's zombie.
    Windows' ``communicate`` times out without the partial output, so it is read
    after the kill, as ``subprocess.run`` does; on POSIX ``exc`` already has it.
    """
    if posix:
        _end_group_gracefully(proc)
    proc.kill()
    if not posix and isinstance(exc, subprocess.TimeoutExpired):
        exc.stdout, exc.stderr = proc.communicate()
        return
    proc.wait()


def _end_group_gracefully(proc: subprocess.Popen[Any]) -> None:
    """SIGTERM ``proc``'s group, wait up to :data:`_TERM_GRACE_S` for it, then SIGKILL the group."""
    _end_groups((proc.pid,), signal.SIGTERM, _TERM_GRACE_S)


def _end_groups(pgids: Collection[int], signum: int, grace_s: float) -> None:
    """Send ``signum`` to each group, wait up to ``grace_s`` for their leaders, then SIGKILL them.

    The SIGKILL always follows: other members of a group may outlive its
    leader, and a second Ctrl-C during the grace must not skip it.
    """
    for pgid in pgids:
        _signal_group(pgid, signum)
    try:
        deadline = time.monotonic() + grace_s
        while not all(map(_leader_exited, pgids)) and time.monotonic() < deadline:
            time.sleep(_LEADER_POLL_S)
    finally:
        for pgid in pgids:
            _signal_group(pgid, signal.SIGKILL)


def _leader_exited(pgid: int) -> bool:
    """Whether the group's leader, a child of this process, has exited (reaped or not).

    Why not ``killpg(pgid, 0)``: on Linux a zombie leader keeps its group
    signalable until ``Popen`` reaps it, and when the handler runs in the thread
    that would reap it, every ending would wait out the whole grace. ``WNOWAIT``
    leaves the zombie for ``Popen``. macOS before Python 3.13 has no ``waitid``;
    there the whole group must be gone, which its ``killpg`` refusing a group of
    one zombie (EPERM) makes reachable.
    """
    waitid = getattr(os, "waitid", None)
    if waitid is None:
        return _group_gone(pgid)
    try:
        state = waitid(os.P_PID, pgid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except ChildProcessError:  # already reaped by its run_bounded thread
        return True
    return state is not None


def _group_gone(pgid: int) -> bool:
    """Whether ``killpg`` finds no group (ESRCH) or, on macOS, a group of one zombie (EPERM)."""
    try:
        os.killpg(pgid, 0)
    except (ProcessLookupError, PermissionError):
        return True
    return False


def _signal_group(pgid: int, signum: int) -> None:
    """``killpg``, ignoring a group that is gone (ESRCH) or holds only a zombie (EPERM, macOS)."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pgid, signum)
