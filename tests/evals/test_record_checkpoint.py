"""The ``--record`` checkpoint: each finished sample saved, and reused only when it still matches.

Pure file I/O on ``tmp_path``; no runner, judge or CLI.
"""

from __future__ import annotations

import json
from pathlib import Path

from coding_agent_playbook.evals.record_checkpoint import (
    RecordCheckpoint,
    default_checkpoint_path,
)
from coding_agent_playbook.evals.release_metrics import SampleRecord

_SETUP = "a" * 64
_INPUTS = "i" * 64


def _record(sample_id: str, *, inputs: str = _INPUTS, graded: str = "head") -> SampleRecord:
    entry = {"inputs_digest": inputs, "graded": graded, "passes": 1, "runs": 2}
    return SampleRecord(sample_id, entry, (100, None), (0.5, None), ("m", "m"))


def _open(path: Path, *, setup: str = _SETUP, resume: bool = True) -> RecordCheckpoint:
    return RecordCheckpoint.open(path, setup_digest=setup, resume=resume)


def test_the_default_checkpoint_sits_beside_the_metrics_file() -> None:
    assert default_checkpoint_path(Path("m/opus.json")) == Path("m/opus.json.partial.jsonl")


def test_each_appended_sample_is_on_disk_and_reused_on_resume(tmp_path: Path) -> None:
    path = tmp_path / "run.partial.jsonl"
    first = _open(path, resume=False)
    first.append("sample", _record("review/a"))
    first.append("control", _record("review/a", graded="v0.1.0"))

    lines = path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == {"checkpoint": 1, "setup_digest": _SETUP}
    assert len(lines) == 3

    again = _open(path)
    assert again.resumable == 2
    assert again.resumed("sample", "review/a", inputs_digest=_INPUTS, graded="head") == _record(
        "review/a"
    )
    control = again.resumed("control", "review/a", inputs_digest=_INPUTS, graded="v0.1.0")
    assert control == _record("review/a", graded="v0.1.0")


def test_a_sample_whose_inputs_or_graded_source_changed_is_not_reused(tmp_path: Path) -> None:
    path = tmp_path / "run.partial.jsonl"
    _open(path, resume=False).append("sample", _record("review/a"))
    again = _open(path)
    assert again.resumed("sample", "review/a", inputs_digest="other", graded="head") is None
    assert again.resumed("sample", "review/a", inputs_digest=_INPUTS, graded="v0.1.0") is None
    assert again.resumed("sample", "review/b", inputs_digest=_INPUTS, graded="head") is None


def test_another_setup_or_no_resume_starts_the_file_over(tmp_path: Path) -> None:
    path = tmp_path / "run.partial.jsonl"
    _open(path, resume=False).append("sample", _record("review/a"))

    assert _open(path, setup="b" * 64).resumable == 0
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1  # the new header only

    _open(path, setup="b" * 64).append("sample", _record("review/a"))
    assert _open(path, setup="b" * 64, resume=False).resumable == 0
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_a_line_a_crash_cut_short_is_dropped(tmp_path: Path) -> None:
    path = tmp_path / "run.partial.jsonl"
    _open(path, resume=False).append("sample", _record("review/a"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"kind": "sample", "sample_id": "review/b", "entr')

    again = _open(path)
    assert again.resumable == 1
    assert "review/b" not in path.read_text(encoding="utf-8")


def test_a_missing_file_resumes_nothing_and_remove_deletes_it(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "run.partial.jsonl"
    checkpoint = _open(path)
    assert checkpoint.resumable == 0
    assert path.is_file()
    checkpoint.remove()
    assert not path.exists()


def test_a_sample_keeps_its_answers_through_the_checkpoint(tmp_path: Path) -> None:
    path = tmp_path / "run.partial.jsonl"
    answer = {"sample": "review/a", "run": 0, "artifact": None, "criteria": []}
    record = SampleRecord("review/a", _record("review/a").entry, (1,), (None,), (), (answer,))
    _open(path, resume=False).append("sample", record)
    kept = _open(path).resumed("sample", "review/a", inputs_digest=_INPUTS, graded="head")
    assert kept is not None
    assert kept.answers == (answer,)


def test_a_line_written_before_answers_reads_as_none(tmp_path: Path) -> None:
    path = tmp_path / "run.partial.jsonl"
    _open(path, resume=False).append("sample", _record("review/a"))
    line = json.loads(path.read_text(encoding="utf-8").splitlines()[1])
    del line["answers"]
    header = json.dumps({"checkpoint": 1, "setup_digest": _SETUP})
    path.write_text(f"{header}\n{json.dumps(line)}\n", encoding="utf-8")
    kept = _open(path).resumed("sample", "review/a", inputs_digest=_INPUTS, graded="head")
    assert kept is not None
    assert kept.answers == ()
