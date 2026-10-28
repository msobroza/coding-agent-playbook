"""``--jobs`` and ``--resume`` scheduling of a record's units (``commands._eval_record_runs``).

The units' samples are stand-ins with only an ``id``, and ``run`` is a plain
function, so nothing here starts a harness or a judge.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from coding_agent_playbook.commands._eval_record_runs import RecordUnit, record_units
from coding_agent_playbook.evals.record_checkpoint import RecordCheckpoint
from coding_agent_playbook.evals.release_metrics import SampleRecord

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
    failed = threading.Event()
    release = threading.Event()
    ran: list[str] = []
    lock = threading.Lock()

    def run(unit: RecordUnit) -> SampleRecord:
        sample_id = unit.sample.id
        with lock:
            ran.append(sample_id)
        if sample_id == "review/a":
            failed.set()
            raise RuntimeError("judge refused review/a")
        if sample_id == "review/b":
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
