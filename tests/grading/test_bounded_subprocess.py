"""``run_bounded``: a bounded child that takes its whole process group with it.

Real processes run here: the behaviour under test is what the OS does to a
process group. Exit codes answer wherever the behaviour allows; only the tests of
a timeout sleep into one.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.grading import bounded_subprocess
from coding_agent_playbook.grading.bounded_subprocess import run_bounded
from tests._process_tree import (
    TIMEOUT_S,
    ignoring_leaf_argv,
    is_alive,
    reaped_grandchild,
    recorded_pid,
    spawning_program,
    wait_for_pid,
)

if TYPE_CHECKING:
    from pathlib import Path

posix_only = pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")


def test_a_finished_run_carries_its_exit_code_and_text_output(tmp_path: Path) -> None:
    program = "import os, sys; print(os.getcwd()); print(os.environ['PB_X'], file=sys.stderr); sys.exit(3)"

    done = run_bounded(
        [sys.executable, "-c", program], cwd=tmp_path, env={**os.environ, "PB_X": "y"}, timeout_s=30
    )

    assert done.returncode == 3
    assert os.path.samefile(done.stdout.strip(), tmp_path)
    assert done.stderr == "y\n"


def test_bytes_mode_feeds_stdin_and_returns_bytes() -> None:
    program = "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read()[::-1])"

    done = run_bounded(
        [sys.executable, "-c", program], input=b"\xffab\x00", text=False, timeout_s=30
    )

    assert (done.returncode, done.stdout) == (0, b"\x00ba\xff")


def test_undecodable_output_is_replaced_when_asked() -> None:
    program = "import sys; sys.stdout.buffer.write(b'0.5\\xff')"

    done = run_bounded(
        [sys.executable, "-c", program], encoding="utf-8", errors="replace", timeout_s=30
    )

    assert done.stdout == "0.5�"


def test_a_missing_program_is_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        run_bounded(["definitely-not-a-real-program-xyz"], timeout_s=30)


@posix_only
def test_a_timed_out_child_takes_its_grandchild_with_it(tmp_path: Path) -> None:
    """Regression: ``subprocess.run`` killed only the child; the grandchild kept running."""
    with reaped_grandchild(tmp_path / "grandchild.pid") as pid_file:
        with pytest.raises(subprocess.TimeoutExpired):
            run_bounded([sys.executable, "-c", spawning_program(pid_file)], timeout_s=TIMEOUT_S)
        assert not is_alive(recorded_pid(pid_file))


@posix_only
def test_a_timeout_keeps_the_partial_output() -> None:
    """``timed_out_run`` grades the partial transcript an agent left at its timeout."""
    program = (
        "import sys, time; print('half'); print('warn', file=sys.stderr); "
        "sys.stdout.flush(); sys.stderr.flush(); time.sleep(60)"
    )

    with pytest.raises(subprocess.TimeoutExpired) as excinfo:
        run_bounded([sys.executable, "-c", program], timeout_s=TIMEOUT_S)

    assert (excinfo.value.stdout, excinfo.value.stderr) == (b"half\n", b"warn\n")


@posix_only
def test_an_interrupt_takes_the_group_with_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In its own session the child misses the terminal's Ctrl-C, so the caller must kill it."""
    pid_file = tmp_path / "grandchild.pid"

    class _InterruptedOnceStarted(subprocess.Popen[Any]):
        def communicate(self, input: Any = None, timeout: float | None = None) -> tuple[Any, Any]:
            wait_for_pid(pid_file)
            raise KeyboardInterrupt

    monkeypatch.setattr(subprocess, "Popen", _InterruptedOnceStarted)
    with reaped_grandchild(pid_file):
        with pytest.raises(KeyboardInterrupt):
            run_bounded([sys.executable, "-c", spawning_program(pid_file)], timeout_s=None)
        assert not is_alive(recorded_pid(pid_file))


@posix_only
def test_an_interrupt_right_after_the_start_takes_the_group_with_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: a Ctrl-C landing between ``Popen`` and the ``try`` left the child running."""
    started: list[int] = []

    class _InterruptedOnAdd(set[int]):
        def add(self, pid: int) -> None:
            started.append(pid)
            raise KeyboardInterrupt

    monkeypatch.setattr(bounded_subprocess, "_live_bounded_groups", _InterruptedOnAdd())
    try:
        with pytest.raises(KeyboardInterrupt):
            run_bounded([sys.executable, "-c", "import time; time.sleep(60)"], timeout_s=None)
        assert not is_alive(started[0], grace_s=1.0)
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(started[0], signal.SIGKILL)


@posix_only
def test_a_normal_exit_ends_the_rest_of_the_group(tmp_path: Path) -> None:
    """Regression: a daemon, MCP server or test helper left in the group outlived the run."""
    pid_file = tmp_path / "background.pid"
    script = f"sleep 60 >/dev/null 2>&1 & echo $! > {pid_file}; echo done"

    with reaped_grandchild(pid_file):
        done = run_bounded(["/bin/sh", "-c", script], timeout_s=30)
        assert (done.returncode, done.stdout, done.stderr) == (0, "done\n", "")
        assert not is_alive(recorded_pid(pid_file), grace_s=1.0)


@posix_only
def test_an_ended_run_leaves_no_live_group() -> None:
    """A stale pid would get a later Ctrl-C once the system reuses its number."""
    run_bounded(["true"], timeout_s=30)
    with pytest.raises(subprocess.TimeoutExpired):
        run_bounded([sys.executable, "-c", "import time; time.sleep(60)"], timeout_s=0.5)

    assert bounded_subprocess._live_bounded_groups == set()


@posix_only
def test_a_member_ignoring_sigterm_gets_the_sigkill_after_the_grace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The leader dies on the SIGTERM; only the group's SIGKILL ends a member that ignores it."""
    pid_file = tmp_path / "member.pid"
    leader = (
        "import subprocess, time; "
        f"subprocess.Popen({ignoring_leaf_argv(pid_file, 'TERM')!r}); time.sleep(60)"
    )
    monkeypatch.setattr(bounded_subprocess, "_TERM_GRACE_S", 0.5)

    with reaped_grandchild(pid_file):
        with pytest.raises(subprocess.TimeoutExpired):
            run_bounded([sys.executable, "-c", leader], timeout_s=TIMEOUT_S)
        assert not is_alive(wait_for_pid(pid_file, limit_s=1.0), grace_s=1.0)


def test_a_halted_thread_starts_no_bounded_child(tmp_path: Path) -> None:
    """After an interrupt, a record's worker must not start its next agent or judge CLI."""
    halt = threading.Event()
    marker = tmp_path / "started"
    halt.set()

    with pytest.raises(bounded_subprocess.BoundedRunHalted, match="touch"):
        bounded_subprocess.halted_by(halt, run_bounded)(["touch", str(marker)], timeout_s=30)

    assert not marker.exists()
    assert run_bounded(["true"], timeout_s=30).returncode == 0  # other threads still run


@posix_only
def test_a_group_kill_refused_by_the_os_still_ends_in_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """macOS refuses ``killpg`` (EPERM) once the group holds only the leader's zombie."""
    started: list[subprocess.Popen[Any]] = []

    class _Recorded(subprocess.Popen[Any]):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            started.append(self)

    def _refused(pid: int, sig: int) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "killpg", _refused)
    monkeypatch.setattr(subprocess, "Popen", _Recorded)
    monkeypatch.setattr(bounded_subprocess, "_TERM_GRACE_S", 0.2)
    with pytest.raises(subprocess.TimeoutExpired):
        run_bounded([sys.executable, "-c", "import time; time.sleep(60)"], timeout_s=1.0)
    assert started[0].returncode == -signal.SIGKILL


@posix_only
def test_a_grandchild_that_left_the_group_cannot_hold_the_timeout_open(tmp_path: Path) -> None:
    """Draining the pipes after the kill would wait for every process that still holds them."""
    program = (
        "import pathlib, subprocess, sys, time; "
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(8)'], "
        "start_new_session=True); "
        f"pathlib.Path({str(tmp_path / 'escaped.pid')!r}).write_text(str(p.pid)); time.sleep(60)"
    )

    with reaped_grandchild(tmp_path / "escaped.pid"):
        started = time.monotonic()
        with pytest.raises(subprocess.TimeoutExpired):
            run_bounded([sys.executable, "-c", program], timeout_s=1.0)
        assert time.monotonic() - started < 6.0


def test_a_windows_timeout_reads_the_output_after_the_kill(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows' ``communicate`` times out without the partial output; ``subprocess.run`` reads it after."""

    class _WindowsTimeout:
        pid = 2**30 - 1  # never a real pid: a killpg on it finds no group
        returncode = None

        def __init__(self, args: Any, **kwargs: Any) -> None:
            self.args = args
            self.communicated = 0

        def __enter__(self) -> _WindowsTimeout:
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

        def communicate(self, input: Any = None, timeout: float | None = None) -> tuple[Any, Any]:
            self.communicated += 1
            if self.communicated == 1:
                raise subprocess.TimeoutExpired(self.args, timeout or 0.0)
            return b"part", b"err"

        def kill(self) -> None:
            self.returncode = 1

        def wait(self, timeout: float | None = None) -> int:
            return 1

    monkeypatch.setattr(bounded_subprocess, "_POSIX", False)
    monkeypatch.setattr(subprocess, "Popen", _WindowsTimeout)

    with pytest.raises(subprocess.TimeoutExpired) as excinfo:
        run_bounded(["agent"], timeout_s=1.0)

    assert (excinfo.value.stdout, excinfo.value.stderr) == (b"part", b"err")
