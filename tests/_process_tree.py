"""A fake CLI whose own child outlives it unless the caller kills its whole process group.

``subprocess.run(timeout=...)`` kills only its direct child on POSIX, so an agent
CLI's workers, a judge CLI's children or a tool's helpers kept running for the
rest of an ``eval --record`` run. A regression test starts
:func:`spawning_program` through the caller under test with a timeout, then
asserts with :func:`is_alive` that the grandchild it recorded died too.
:func:`reaped_grandchild` kills a survivor whatever the test's outcome.

The signal tests chain bounded runs instead: :func:`bounded_parent_program` runs
:func:`leaf_argv` (or another bounded parent) through ``run_bounded``, and
:func:`own_group` starts the outermost one in a process group of its own, as a
terminal starts a job, so a test can signal its group as a terminal or a
supervisor would.

Example::

    with reaped_grandchild(tmp_path / "grandchild.pid") as pid_file:
        run_the_caller([sys.executable, "-c", spawning_program(pid_file)], timeout_s=3.0)
        assert not is_alive(int(pid_file.read_text()))
"""

from __future__ import annotations

import contextlib
import os
import shlex
import signal
import subprocess
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from pathlib import Path

#: A bound the fake CLI always outlives yet starts its grandchild well within, on a
#: loaded CI runner too.
TIMEOUT_S = 3.0


def spawning_program(pid_file: Path) -> str:
    """Python source that starts a sleeping grandchild, writes its pid to ``pid_file``, then sleeps.

    Example: ``[sys.executable, "-c", spawning_program(tmp_path / "grandchild.pid")]``.
    """
    return (
        "import pathlib, subprocess, sys, time; "
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid)); time.sleep(60)"
    )


@contextlib.contextmanager
def reaped_grandchild(pid_file: Path) -> Iterator[Path]:
    """Yield ``pid_file``; afterwards kill the grandchild it names, if it still runs."""
    try:
        yield pid_file
    finally:
        if pid_file.is_file():
            with contextlib.suppress(ProcessLookupError, ValueError):
                os.kill(int(pid_file.read_text(encoding="utf-8")), signal.SIGKILL)


def recorded_pid(pid_file: Path) -> int:
    """The grandchild pid the fake CLI wrote to ``pid_file``."""
    return int(pid_file.read_text(encoding="utf-8").strip())


def leaf_argv(pid_file: Path) -> list[str]:
    """A shell that writes its pid to ``pid_file`` and becomes ``sleep 60``: the innermost CLI."""
    return ["/bin/sh", "-c", f"echo $$ > {shlex.quote(str(pid_file))}; exec sleep 60"]


def ignoring_leaf_argv(pid_file: Path, signame: str) -> list[str]:
    """:func:`leaf_argv` with ``signame`` (``TERM``, ``INT``) ignored: a CLI only a SIGKILL ends."""
    return ["/bin/sh", "-c", f"trap '' {signame}; {leaf_argv(pid_file)[2]}"]


#: Why: a background job of a non-interactive shell starts with SIGINT ignored, and
#: a child inherits that; the processes under test must see what a terminal's
#: foreground job sees.
_DEFAULT_SIGNALS = (
    "import signal",
    "signal.signal(signal.SIGINT, signal.default_int_handler)",
    "signal.signal(signal.SIGTERM, signal.SIG_DFL)",
    "signal.signal(signal.SIGHUP, signal.SIG_DFL)",
    "from coding_agent_playbook.grading import bounded_subprocess",
)


def bounded_parent_program(
    child_argv: Sequence[str], *, in_thread: bool = False, grace_file: Path | None = None
) -> str:
    """Python source that runs ``child_argv`` through ``run_bounded`` (timeout 60 s).

    ``in_thread`` runs it from a worker thread while the main thread joins, as
    ``eval --record --jobs N`` does, after installing the forwarding the CLI entry
    point installs. ``grace_file`` gets, before the child starts, the grace the
    process would give its groups after a SIGTERM.
    Example: ``[sys.executable, "-c", bounded_parent_program(leaf_argv(f))]``.
    """
    call = f"bounded_subprocess.run_bounded({list(child_argv)!r}, timeout_s=60.0)"
    if grace_file is not None:
        call = (
            f"__import__('pathlib').Path({str(grace_file)!r}).write_text("
            f"repr(bounded_subprocess._own_term_grace_s()))\n{call}"
        )
    if not in_thread:
        return "\n".join((*_DEFAULT_SIGNALS, call))
    threaded = (
        "import threading",
        "bounded_subprocess.forward_signals_to_bounded_children()",
        f"worker = threading.Thread(target=lambda: {call})",
        "worker.start()",
        "worker.join()",
    )
    return "\n".join((*_DEFAULT_SIGNALS, *threaded))


@contextlib.contextmanager
def own_group(program: str, *, new_session: bool = False) -> Iterator[subprocess.Popen[bytes]]:
    """Start ``python -c program`` in a process group of its own; afterwards kill the group.

    A group, as a terminal starts a job; ``new_session`` leads a session of its
    own too, as ``setsid``, a service manager or a container's init starts it.
    """
    proc = subprocess.Popen(
        [sys.executable, "-c", program],
        stdin=subprocess.DEVNULL,
        start_new_session=new_session,
        process_group=None if new_session else 0,
    )
    try:
        yield proc
    finally:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()


def wait_for_pid(pid_file: Path, limit_s: float = 30.0) -> int:
    """Block until a process has written its pid to ``pid_file``, then return it."""
    deadline = time.monotonic() + limit_s
    while not pid_file.is_file() or not pid_file.read_text(encoding="utf-8").strip():
        if time.monotonic() > deadline:
            raise AssertionError(f"{pid_file} never got a pid within {limit_s:g}s")
        time.sleep(0.05)
    return recorded_pid(pid_file)


def is_alive(pid: int, grace_s: float = 5.0) -> bool:
    """Whether ``pid`` still runs after ``grace_s`` seconds for the kernel to reap it."""
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        time.sleep(0.1)
    return True
