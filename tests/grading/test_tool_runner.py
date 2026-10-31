"""The evaluator ``ToolRunner`` seam (prK §F.2.1): bounded subprocess, per-run memo.

``run_bounded`` is replaced by a named fake for the seam tests; no process starts.
Only the process-group regression runs a real one.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.grading import bounded_subprocess
from coding_agent_playbook.grading.tool_runner import (
    MemoToolRunner,
    ToolRunError,
    subprocess_tool_runner,
)
from tests._process_tree import (
    TIMEOUT_S,
    is_alive,
    reaped_grandchild,
    recorded_pid,
    spawning_program,
)
from tests.fakes import FakeRuffRunner


@dataclass
class FakeBoundedRun:
    """Stands in for ``run_bounded``: records kwargs, then answers or raises ``error``."""

    error: BaseException | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append({"argv": argv, **kwargs})
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(argv, 0, b"[]", b"noise")


def test_subprocess_runner_bounds_and_feeds_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeBoundedRun()
    monkeypatch.setattr(bounded_subprocess, "run_bounded", fake)

    answer = subprocess_tool_runner(["ruff", "check", "-"], b"x = 1\n", Path("/r"), 4.0)

    [call] = fake.calls
    assert answer == (0, b"[]")
    assert (call["input"], call["cwd"], call["timeout_s"]) == (b"x = 1\n", Path("/r"), 4.0)
    assert call["text"] is False


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (subprocess.TimeoutExpired(["ruff"], 4.0), "ruff timed out after 4s"),
        (FileNotFoundError("no ruff"), "ruff could not run: no ruff"),
    ],
    ids=["timeout", "missing"],
)
def test_subprocess_runner_failure_is_tool_run_error(
    monkeypatch: pytest.MonkeyPatch, error: BaseException, message: str
) -> None:
    monkeypatch.setattr(bounded_subprocess, "run_bounded", FakeBoundedRun(error=error))

    with pytest.raises(ToolRunError) as excinfo:
        subprocess_tool_runner(["ruff", "check", "-"], b"", None, 4.0)

    assert str(excinfo.value) == message


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")
def test_a_timed_out_tool_takes_its_child_processes_with_it(tmp_path: Path) -> None:
    """Regression: the timeout killed the tool only; a helper it started kept running."""
    with reaped_grandchild(tmp_path / "grandchild.pid") as pid_file:
        argv = [sys.executable, "-c", spawning_program(pid_file)]
        with pytest.raises(ToolRunError, match="timed out"):
            subprocess_tool_runner(argv, b"", None, TIMEOUT_S)
        assert not is_alive(recorded_pid(pid_file))


def test_memo_runs_each_distinct_call_once() -> None:
    inner = FakeRuffRunner()
    memo = MemoToolRunner(inner)

    memo(["ruff", "-"], b"a\n", None, 1.0)
    memo(["ruff", "-"], b"a\n", None, 1.0)
    memo(["ruff", "-"], b"b\n", None, 1.0)

    assert [stdin for _, stdin, _, _ in inner.calls] == ["a\n", "b\n"]


def test_memo_never_remembers_a_failure() -> None:
    inner = FakeRuffRunner(timeout=True)
    memo = MemoToolRunner(inner)

    for _ in range(2):
        with pytest.raises(ToolRunError):
            memo(["ruff", "-"], b"a\n", None, 1.0)

    assert len(inner.calls) == 2
