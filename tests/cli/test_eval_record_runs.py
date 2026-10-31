"""``--jobs`` and ``--resume`` scheduling of a record's units (``commands._eval_record_runs``).

The units' samples are stand-ins with only an ``id``, and ``run`` is a plain
function, so nothing here starts a harness or a judge. The Ctrl-C test runs a
record in a process of its own whose units start shell leaves through
``run_bounded``, as the agent and judge runners do.
"""

from __future__ import annotations

import contextlib
import os
import signal
import threading
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from coding_agent_playbook.commands._eval_record_runs import RecordUnit, record_units
from coding_agent_playbook.evals.record_checkpoint import RecordCheckpoint
from coding_agent_playbook.evals.release_metrics import SampleRecord
from tests._process_tree import is_alive, own_group, reaped_grandchild, wait_for_pid

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evals.sample import EvalSample

_INPUTS = "i" * 64
#: Bounds every wait, so a scheduling bug fails the test instead of hanging it.
_WAIT = 10.0


def _unit(sample_id: str, index: int = 0) -> RecordUnit:
    sample = cast("EvalSample", SimpleNamespace(id=sample_id))
    return RecordUnit("sample", sample, index, _INPUTS)


def _record(sample_id: str) -> SampleRecord:
    entry = {"inputs_digest": _INPUTS, "graded": "head", "passes": 1, "runs": 1}
    return SampleRecord(sample_id, entry, (1,), (None,), ())


def _checkpoint(tmp_path: Path, *, resume: bool = False) -> RecordCheckpoint:
    return RecordCheckpoint.open(tmp_path / "c.jsonl", setup_digest="s", resume=resume)


def test_jobs_run_units_at_the_same_time_and_save_each(tmp_path: Path) -> None:
    # Four units that each wait for the other three can only finish on four threads.
    together = threading.Barrier(4, timeout=_WAIT)

    def run(unit: RecordUnit) -> SampleRecord:
        together.wait()
        return _record(unit.sample.id)

    units = [_unit(f"review/{name}", i) for i, name in enumerate("abcd")]
    records = record_units(units, jobs=4, run=run, checkpoint=_checkpoint(tmp_path))

    assert sorted(records) == [("sample", f"review/{name}") for name in "abcd"]
    assert _checkpoint(tmp_path, resume=True).resumable == 4


def test_resumed_units_are_not_run_again(tmp_path: Path) -> None:
    _checkpoint(tmp_path).append("sample", _record("review/a"))
    ran: list[str] = []

    def run(unit: RecordUnit) -> SampleRecord:
        ran.append(unit.sample.id)
        return _record(unit.sample.id)

    units = [_unit("review/a"), _unit("review/b", 1)]
    records = record_units(units, jobs=1, run=run, checkpoint=_checkpoint(tmp_path, resume=True))

    assert ran == ["review/b"]
    assert set(records) == {("sample", "review/a"), ("sample", "review/b")}


def test_a_failure_saves_the_running_units_and_starts_no_queued_one(tmp_path: Path) -> None:
    b_running = threading.Event()
    failed = threading.Event()
    release = threading.Event()
    ran: list[str] = []
    lock = threading.Lock()

    def run(unit: RecordUnit) -> SampleRecord:
        sample_id = unit.sample.id
        with lock:
            ran.append(sample_id)
        if sample_id == "review/a":
            # Fail only once review/b runs, or the pool may cancel it before it starts.
            assert b_running.wait(_WAIT)
            failed.set()
            raise RuntimeError("judge refused review/a")
        if sample_id == "review/b":
            b_running.set()
            assert failed.wait(_WAIT)  # still running when review/a fails
        else:
            assert release.wait(_WAIT)
        return _record(sample_id)

    threading.Timer(0.5, release.set).start()
    units = [_unit(f"review/{name}", i) for i, name in enumerate("abcdef")]
    checkpoint = _checkpoint(tmp_path)

    with pytest.raises(RuntimeError, match="review/a"):
        record_units(units, jobs=2, run=run, checkpoint=checkpoint)

    # Each of the 2 workers takes at most one more unit before the queue is cancelled.
    assert len(ran) <= 4
    assert "review/f" not in ran
    saved = _checkpoint(tmp_path, resume=True)
    assert saved.resumed("sample", "review/b", inputs_digest=_INPUTS, graded="head") is not None
    assert saved.resumable == len(ran) - 1  # every unit that ran, but the failed one


#: A record of 4 units on 2 workers; each unit starts an "agent" then a "judge"
#: leaf through ``run_bounded``. A leaf ignores SIGINT, as a CLI that traps Ctrl-C
#: does, so only the record's own ending stops it.
_INTERRUPTED_RECORD = """
import pathlib, signal
signal.signal(signal.SIGINT, signal.default_int_handler)
from types import SimpleNamespace
from coding_agent_playbook.commands._eval_record_runs import RecordUnit, record_units
from coding_agent_playbook.evals.record_checkpoint import RecordCheckpoint
from coding_agent_playbook.grading import bounded_subprocess
bounded_subprocess.forward_signals_to_bounded_children()
work = pathlib.Path({work!r})
def run(unit):
    for step in ("agent", "judge"):
        script = f"trap '' INT; echo $$ > {{work}}/{{unit.sample.id}}.{{step}}; exec sleep 60"
        bounded_subprocess.run_bounded(["/bin/sh", "-c", script], timeout_s=60)
    raise AssertionError("a unit outlived the interrupt")
units = [RecordUnit("sample", SimpleNamespace(id=f"u{{i}}"), i, "i" * 64) for i in range(4)]
checkpoint = RecordCheckpoint.open(work / "c.jsonl", setup_digest="s", resume=False)
record_units(units, jobs=2, run=run, checkpoint=checkpoint)
"""


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")
def test_ctrl_c_under_jobs_starts_no_queued_unit_and_ends_the_running_ones(
    tmp_path: Path,
) -> None:
    """Regression: the pool's exit waited for the running units, then started every queued one."""
    leaf_files = [tmp_path / f"u{i}.{step}" for i in range(4) for step in ("agent", "judge")]

    with contextlib.ExitStack() as stack:
        for leaf_file in leaf_files:
            stack.enter_context(reaped_grandchild(leaf_file))
        proc = stack.enter_context(own_group(_INTERRUPTED_RECORD.format(work=str(tmp_path))))
        agents = [wait_for_pid(tmp_path / f"u{i}.agent") for i in (0, 1)]
        os.killpg(proc.pid, signal.SIGINT)

        assert proc.wait(timeout=20) == -signal.SIGINT
        assert sorted(f.name for f in leaf_files if f.exists()) == ["u0.agent", "u1.agent"]
        assert not any(is_alive(pid, grace_s=1.0) for pid in agents)


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")
def test_sigterm_under_jobs_leaves_no_bounded_child_running(tmp_path: Path) -> None:
    """Regression: a judge started during the SIGTERM handler's grace outlived the record.

    Each agent leaf dies on the SIGTERM, so its worker went on to start its judge
    in a group the handler's snapshot of the live groups did not hold.
    """
    leaf_files = [tmp_path / f"u{i}.{step}" for i in range(4) for step in ("agent", "judge")]

    with contextlib.ExitStack() as stack:
        for leaf_file in leaf_files:
            stack.enter_context(reaped_grandchild(leaf_file))
        proc = stack.enter_context(own_group(_INTERRUPTED_RECORD.format(work=str(tmp_path))))
        for i in (0, 1):
            wait_for_pid(tmp_path / f"u{i}.agent")
        os.killpg(proc.pid, signal.SIGTERM)

        assert proc.wait(timeout=20) == -signal.SIGTERM
        time.sleep(1.0)  # a leaf started at the end has written its pid by now
        started = [wait_for_pid(f, limit_s=1.0) for f in leaf_files if f.exists()]
        assert [pid for pid in started if is_alive(pid, grace_s=0.5)] == []
