"""Hook latency budgets over real interpreter launches (specs/prK-lifecycle-hooks.md §D.1, §D.9).

Wall-clock percentiles over spawned interpreters are neither fast nor
repeatable on shared runners, so the real budget test is gated behind
``PLAYBOOK_LATENCY_TESTS=1`` (like ``PLAYBOOK_E2E_CLAUDE``) and asserts the
**excess** over a bare ``python -I -c pass`` start (OQ-26). The default run
keeps one N = 3 smoke per path with a generous bound, 10x the budget, which
still catches an accidental heavy import on the dispatch path.
"""

from __future__ import annotations

import os
import statistics
import sys
import time
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.hook_runtime.dispatch.event import EventName
from tests.hook_runtime.guard_repo import GuardRepo, hook_record
from tests.import_probe import PROBE_TIMEOUT_S, probe_env

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.dispatch.proc import SubprocessProc

GATED: Final = os.environ.get("PLAYBOOK_LATENCY_TESTS") == "1"
#: path -> (event, tool, absolute budget in s, gated excess over the interpreter floor in s)
PATHS: Final = {
    "pre_tool_use-edit": (EventName.PRE_TOOL_USE, "Edit", 0.1, 0.06),
    "pre_tool_use-bash": (EventName.PRE_TOOL_USE, "Bash", 0.1, 0.06),
    "session_start": (EventName.SESSION_START, None, 0.3, 0.26),
}


@pytest.fixture
def synced(tmp_path: Path) -> GuardRepo:
    repo = GuardRepo.create(tmp_path)
    repo.install(
        hook_record("guard-a", events=["pre_tool_use"], priority=1),
        hook_record("lint-q", events=["pre_tool_use", "session_start"], on_error="open"),
    )
    return repo


def _timed(proc: SubprocessProc, argv: list[str], *, repo: GuardRepo, payload: bytes) -> float:
    env = {**probe_env(), "CLAUDE_PROJECT_DIR": str(repo.root)}
    started = time.perf_counter()
    result = proc.run(argv, timeout=PROBE_TIMEOUT_S, env=env, input=payload, cwd=str(repo.root))
    elapsed = time.perf_counter() - started
    assert result.returncode == 0, result.stderr.decode()
    return elapsed


def _dispatch_argv(event: EventName) -> list[str]:
    return [
        sys.executable,
        "-I",
        "-m",
        "coding_agent_playbook.hook_runtime",
        "dispatch",
        event.value,
        "--harness",
        "claude_code",
    ]


def _p95(samples: list[float]) -> float:
    return statistics.quantiles(samples, n=20)[-1] if len(samples) > 1 else samples[0]


@pytest.mark.parametrize("path", sorted(PATHS))
def test_dispatch_smoke_stays_within_ten_times_the_budget(
    synced: GuardRepo, real_proc: SubprocessProc, path: str
) -> None:
    event, tool, budget_s, _ = PATHS[path]
    payload = synced.payload(event, tool=tool)

    samples = [
        _timed(real_proc, _dispatch_argv(event), repo=synced, payload=payload) for _ in range(3)
    ]

    assert min(samples) <= 10 * budget_s, samples


@pytest.mark.skipif(not GATED, reason="set PLAYBOOK_LATENCY_TESTS=1 to measure latency budgets")
@pytest.mark.parametrize("path", sorted(PATHS))
def test_dispatch_excess_over_interpreter_start_meets_the_budget(
    synced: GuardRepo, real_proc: SubprocessProc, path: str
) -> None:  # pragma: no cover - gated wall-clock measurement
    event, tool, _, excess_s = PATHS[path]
    payload = synced.payload(event, tool=tool)
    floor = [
        _timed(real_proc, [sys.executable, "-I", "-c", "pass"], repo=synced, payload=b"")
        for _ in range(25)
    ]

    samples = [
        _timed(real_proc, _dispatch_argv(event), repo=synced, payload=payload) for _ in range(25)
    ]

    assert _p95(samples) - _p95(floor) <= excess_s, (samples, floor)
