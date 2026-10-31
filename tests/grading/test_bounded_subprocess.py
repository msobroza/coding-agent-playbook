"""``run_bounded``: a bounded child that takes its whole process group with it.

Real processes run here: the behaviour under test is what the OS does to a
process group. Exit codes answer wherever the behaviour allows; only the tests of
a timeout sleep into one.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.grading.bounded_subprocess import run_bounded
from tests._process_tree import (
    TIMEOUT_S,
    is_alive,
    reaped_grandchild,
    recorded_pid,
    spawning_program,
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
            _wait_for(pid_file)
            raise KeyboardInterrupt

    monkeypatch.setattr(subprocess, "Popen", _InterruptedOnceStarted)
    with reaped_grandchild(pid_file):
        with pytest.raises(KeyboardInterrupt):
            run_bounded([sys.executable, "-c", spawning_program(pid_file)], timeout_s=None)
        assert not is_alive(recorded_pid(pid_file))


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
    with pytest.raises(subprocess.TimeoutExpired):
        run_bounded([sys.executable, "-c", "import time; time.sleep(60)"], timeout_s=1.0)
    assert started[0].returncode == -signal.SIGKILL


def _wait_for(path: Path, limit_s: float = 30.0) -> None:
    """Block until ``path`` exists: the fake CLI has started its grandchild."""
    deadline = time.monotonic() + limit_s
    while not path.is_file() or not path.read_text(encoding="utf-8"):
        if time.monotonic() > deadline:
            raise AssertionError(f"{path} never appeared")
        time.sleep(0.05)
