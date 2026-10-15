"""The evaluator ``ToolRunner`` seam (prK §F.2.1): bounded subprocess, per-run memo.

``subprocess.run`` is replaced by a named fake for each test; no process starts.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.evaluators.tool_runner import (
    MemoToolRunner,
    ToolRunError,
    subprocess_tool_runner,
)
from tests.fakes import FakeRuffRunner


@dataclass
class FakeSubprocessRun:
    """Stands in for ``subprocess.run``: records kwargs, then answers or raises ``error``."""

    error: BaseException | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append({"argv": argv, **kwargs})
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(argv, 0, b"[]", b"noise")


def test_subprocess_runner_bounds_and_feeds_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSubprocessRun()
    monkeypatch.setattr(subprocess, "run", fake)

    answer = subprocess_tool_runner(["ruff", "check", "-"], b"x = 1\n", Path("/r"), 4.0)

    [call] = fake.calls
    assert answer == (0, b"[]")
    assert (call["input"], call["cwd"], call["timeout"]) == (b"x = 1\n", Path("/r"), 4.0)


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
    monkeypatch.setattr(subprocess, "run", FakeSubprocessRun(error=error))

    with pytest.raises(ToolRunError) as excinfo:
        subprocess_tool_runner(["ruff", "check", "-"], b"", None, 4.0)

    assert str(excinfo.value) == message


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
