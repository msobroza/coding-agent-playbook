"""A fake CLI whose own child outlives it unless the caller kills its whole process group.

``subprocess.run(timeout=...)`` kills only its direct child on POSIX, so an agent
CLI's workers, a judge CLI's children or a tool's helpers kept running for the
rest of an ``eval --record`` run. A regression test starts
:func:`spawning_program` through the caller under test with a timeout, then
asserts with :func:`is_alive` that the grandchild it recorded died too.
:func:`reaped_grandchild` kills a survivor whatever the test's outcome.

Example::

    with reaped_grandchild(tmp_path / "grandchild.pid") as pid_file:
        run_the_caller([sys.executable, "-c", spawning_program(pid_file)], timeout_s=3.0)
        assert not is_alive(int(pid_file.read_text()))
"""

from __future__ import annotations

import contextlib
import os
import signal
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
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
    return int(pid_file.read_text(encoding="utf-8"))


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
