"""``run_bounded``'s child gets the signals its parent gets, through every nesting level.

In a session of its own a bounded child no longer shares its parent's process
group, so a terminal's Ctrl-C, a supervisor's ``kill -TERM -<pgid>`` or a hangup
reached only the playbook process: a worker thread's child, or a nested run's
agent CLI, kept running. Real processes run here: :func:`leaf_argv` is the
innermost CLI and :func:`bounded_parent_program` the playbook processes above it.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import warnings
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.grading import bounded_subprocess
from tests._process_tree import (
    TIMEOUT_S,
    bounded_parent_program,
    ignoring_leaf_argv,
    is_alive,
    leaf_argv,
    own_group,
    reaped_grandchild,
    wait_for_pid,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")

_FORWARDED = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


def test_a_nested_timeout_reaches_the_inner_runs_child(tmp_path: Path) -> None:
    """Regression: the outer SIGKILL gave the middle run no chance to end its own group."""
    middle = bounded_parent_program(leaf_argv(tmp_path / "leaf.pid"))

    with reaped_grandchild(tmp_path / "leaf.pid") as leaf_pid_file:
        with pytest.raises(subprocess.TimeoutExpired):
            bounded_subprocess.run_bounded([sys.executable, "-c", middle], timeout_s=TIMEOUT_S)
        assert not is_alive(wait_for_pid(leaf_pid_file, limit_s=1.0))


def test_ctrl_c_reaches_a_nested_runs_child(tmp_path: Path) -> None:
    """Regression: Ctrl-C reached the top process only; the agent CLI two levels down survived."""
    middle = bounded_parent_program(leaf_argv(tmp_path / "leaf.pid"))
    top = bounded_parent_program([sys.executable, "-c", middle])

    with reaped_grandchild(tmp_path / "leaf.pid") as leaf_pid_file, own_group(top) as proc:
        leaf = wait_for_pid(leaf_pid_file)
        os.killpg(proc.pid, signal.SIGINT)
        assert not is_alive(leaf)


def test_ctrl_c_still_interrupts_the_parent(tmp_path: Path) -> None:
    """Forwarding must not swallow Ctrl-C: the parent itself still dies of SIGINT."""
    parent = bounded_parent_program(leaf_argv(tmp_path / "leaf.pid"))

    with reaped_grandchild(tmp_path / "leaf.pid") as leaf_pid_file, own_group(parent) as proc:
        wait_for_pid(leaf_pid_file)
        os.killpg(proc.pid, signal.SIGINT)
        assert proc.wait(timeout=20) == -signal.SIGINT


def test_a_nested_timeout_ends_a_leaf_that_ignores_sigterm(tmp_path: Path) -> None:
    """Regression: the middle run forwarded the SIGTERM and died at once; the leaf survived it."""
    middle = bounded_parent_program(ignoring_leaf_argv(tmp_path / "leaf.pid", "TERM"))

    with reaped_grandchild(tmp_path / "leaf.pid") as leaf_pid_file:
        with pytest.raises(subprocess.TimeoutExpired):
            bounded_subprocess.run_bounded([sys.executable, "-c", middle], timeout_s=TIMEOUT_S)
        assert not is_alive(wait_for_pid(leaf_pid_file, limit_s=1.0), grace_s=1.0)


def test_an_outer_sigterm_ends_a_nested_leaf_that_ignores_sigterm(tmp_path: Path) -> None:
    """Regression: each level forwarded the SIGTERM and died, so nobody sent the leaf a SIGKILL."""
    middle = bounded_parent_program(ignoring_leaf_argv(tmp_path / "leaf.pid", "TERM"))
    top = bounded_parent_program([sys.executable, "-c", middle])

    with reaped_grandchild(tmp_path / "leaf.pid") as leaf_pid_file, own_group(top) as proc:
        leaf = wait_for_pid(leaf_pid_file)
        os.killpg(proc.pid, signal.SIGTERM)
        assert proc.wait(timeout=20) == -signal.SIGTERM
        assert not is_alive(leaf, grace_s=1.0)


def test_a_session_leading_top_gives_its_nested_child_the_longer_grace(tmp_path: Path) -> None:
    """Regression: a top run under ``setsid`` took the nested grace, tying with its child's.

    With both at half the grace, a leaf that ignores SIGTERM could outlive the
    middle's SIGKILL and the top's (1 run in 5); the graces show the tie at once.
    """
    leaf_pid_file, top_grace, middle_grace = (tmp_path / n for n in ("leaf", "top", "middle"))
    middle = bounded_parent_program(
        ignoring_leaf_argv(leaf_pid_file, "TERM"), grace_file=middle_grace
    )
    top = bounded_parent_program([sys.executable, "-c", middle], grace_file=top_grace)

    full = bounded_subprocess._TERM_GRACE_S
    with reaped_grandchild(leaf_pid_file), own_group(top, new_session=True) as proc:
        leaf = wait_for_pid(leaf_pid_file)
        graces = (float(top_grace.read_text()), float(middle_grace.read_text()))
        assert graces == (full, full / 2)
        os.killpg(proc.pid, signal.SIGTERM)
        assert proc.wait(timeout=20) == -signal.SIGTERM
        assert not is_alive(leaf, grace_s=1.0)


def test_a_forked_child_forgets_its_parents_bounded_groups() -> None:
    """Regression: a forked worker inherited the live set; terminating it ended our runs.

    Nor does it inherit a terminating parent's switch, which would refuse its runs.
    """
    parents_group = 2**30 - 1  # never a real pid: only its presence in the set matters
    bounded_subprocess._live_bounded_groups.add(parents_group)
    bounded_subprocess._process_terminating.set()
    try:
        with warnings.catch_warnings():
            # Why: Python warns that forking a multi-threaded process (pytest's) may deadlock.
            warnings.simplefilter("ignore", DeprecationWarning)
            pid = os.fork()
        if pid == 0:
            terminating = bounded_subprocess._process_terminating.is_set()
            os._exit(len(bounded_subprocess._live_bounded_groups) + 10 * terminating)
        _, status = os.waitpid(pid, 0)
    finally:
        bounded_subprocess._live_bounded_groups.discard(parents_group)
        bounded_subprocess._process_terminating.clear()
    assert os.waitstatus_to_exitcode(status) == 0


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM], ids=["SIGINT", "SIGTERM"])
def test_a_worker_threads_child_gets_the_parents_signal(
    tmp_path: Path, signum: signal.Signals
) -> None:
    """Regression: ``eval --record --jobs N`` runs agent CLIs from worker threads."""
    parent = bounded_parent_program(leaf_argv(tmp_path / "leaf.pid"), in_thread=True)

    with reaped_grandchild(tmp_path / "leaf.pid") as leaf_pid_file, own_group(parent) as proc:
        leaf = wait_for_pid(leaf_pid_file)
        os.killpg(proc.pid, signum)
        assert not is_alive(leaf)
        if signum == signal.SIGTERM:
            assert proc.wait(timeout=10) == -signal.SIGTERM


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGHUP], ids=["SIGTERM", "SIGHUP"])
def test_a_terminating_signal_reaches_the_child_and_still_ends_the_parent(
    tmp_path: Path, signum: signal.Signals
) -> None:
    """Regression: the parent died on the default action and orphaned its child."""
    parent = bounded_parent_program(leaf_argv(tmp_path / "leaf.pid"))

    with reaped_grandchild(tmp_path / "leaf.pid") as leaf_pid_file, own_group(parent) as proc:
        leaf = wait_for_pid(leaf_pid_file)
        os.killpg(proc.pid, signum)
        assert not is_alive(leaf)
        assert proc.wait(timeout=10) == -signum


@pytest.fixture
def default_dispositions() -> Iterator[None]:
    """Start from the dispositions a fresh process has; restore the test process's afterwards."""
    saved = {signum: signal.getsignal(signum) for signum in _FORWARDED}
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGHUP, signal.SIG_DFL)
    try:
        yield
    finally:
        for signum, handler in saved.items():
            signal.signal(signum, handler)


@pytest.mark.usefixtures("default_dispositions")
def test_forwarding_replaces_only_a_default_disposition() -> None:
    """A custom handler is the program's own choice, and ``SIG_IGN`` is ``nohup``'s."""

    def custom(signum: int, frame: object) -> None:
        """A program's own SIGTERM handler."""

    signal.signal(signal.SIGTERM, custom)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)

    bounded_subprocess.forward_signals_to_bounded_children()

    assert signal.getsignal(signal.SIGINT) not in (signal.default_int_handler, None)
    assert signal.getsignal(signal.SIGTERM) is custom
    assert signal.getsignal(signal.SIGHUP) == signal.SIG_IGN


@pytest.mark.usefixtures("default_dispositions")
def test_forwarding_installs_once_and_only_from_the_main_thread() -> None:
    """``signal.signal`` raises off the main thread; a second install must not wrap the first."""
    worker = threading.Thread(target=bounded_subprocess.forward_signals_to_bounded_children)
    worker.start()
    worker.join()
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL

    bounded_subprocess.forward_signals_to_bounded_children()
    installed = [signal.getsignal(signum) for signum in _FORWARDED]
    bounded_subprocess.forward_signals_to_bounded_children()

    assert [signal.getsignal(signum) for signum in _FORWARDED] == installed
    assert len(set(map(id, installed))) == 1
    assert installed[1] != signal.SIG_DFL
