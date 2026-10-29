"""The answers store: one gzip JSON line per stored run (spec D8)."""

from __future__ import annotations

import gzip
import json
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.answers_store import (
    AnswersError,
    ArtifactRef,
    CapturingJudge,
    StoredCriterion,
    StoredRun,
    answers_path,
    read_answers,
    write_answers,
)
from coding_agent_playbook.evals.judge import StubJudge
from coding_agent_playbook.exit_two import ExitTwoError

if TYPE_CHECKING:
    from pathlib import Path

_JUDGE = {"judge": "stub", "judge_model": "m-1"}


def _run(sample: str = "s-a", run: int = 0, **overrides: object) -> StoredRun:
    fields: dict[str, object] = {
        "sample": sample,
        "inputs_digest": "d" * 64,
        "run": run,
        "artifact": "the graded transcript",
        "checks": {"file-exists": 1.0, "tests": 0.5},
        "criteria": (StoredCriterion("is correct", 2.0, 0.75, 1),),
        "judge": _JUDGE,
    }
    fields.update(overrides)
    return StoredRun(**fields)  # type: ignore[arg-type]


def test_round_trip_keeps_every_field(tmp_path: Path) -> None:
    path = answers_path(tmp_path, "9.9.2", "opencode-qwen")
    runs = [
        _run(),
        _run("s-b", 1, artifact=None, artifact_ref=ArtifactRef("9.9.1", "claude-opus")),
    ]

    write_answers(path, runs)

    assert path == tmp_path / "9.9.2" / "answers" / "opencode-qwen.jsonl.gz"
    assert read_answers(path) == runs


def test_the_file_is_gzip_one_line_per_run_sorted(tmp_path: Path) -> None:
    path = tmp_path / "answers.jsonl.gz"

    write_answers(path, [_run("s-b", 0), _run("s-a", 1), _run("s-a", 0)])

    with gzip.open(path, "rt", encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    keys = [(json.loads(line)["sample"], json.loads(line)["run"]) for line in lines]
    assert keys == [("s-a", 0), ("s-a", 1), ("s-b", 0)]


def test_a_fail_fast_run_stores_null_scores_and_no_artifact(tmp_path: Path) -> None:
    path = tmp_path / "answers.jsonl.gz"
    skipped = _run(artifact=None, criteria=(StoredCriterion("is correct", 2.0, None, 1),))

    write_answers(path, [skipped])

    with gzip.open(path, "rt", encoding="utf-8") as handle:
        line = json.loads(handle.readline())
    assert line["artifact"] is None
    assert line["criteria"] == [{"criterion": "is correct", "weight": 2.0, "score": None, "n": 1}]
    assert "artifact_ref" not in line
    assert read_answers(path) == [skipped]


def test_a_bad_line_names_the_path_and_line(tmp_path: Path) -> None:
    path = tmp_path / "answers.jsonl.gz"
    write_answers(path, [_run()])
    with gzip.open(path, "at", encoding="utf-8") as handle:
        handle.write('{"sample": "s-b"}\n')

    with pytest.raises(AnswersError, match=r"answers\.jsonl\.gz:2") as raised:
        read_answers(path)
    assert isinstance(raised.value, ExitTwoError)


def test_capturing_judge_records_calls_and_returns_the_inner_score() -> None:
    judge = CapturingJudge(StubJudge(default=0.7))

    score = judge.score_criterion("is correct", ["a", "diff"], n=3)

    assert score == 0.7
    assert judge.calls == [("is correct", "['a', 'diff']", 0.7, 3)]


def _corrupt_deflate(text: str) -> bytes:
    # gzip.compress writes a 10-byte header (no file name), so byte 10 starts the
    # deflate data; flipping it makes zlib raise zlib.error, not an OSError.
    data = bytearray(gzip.compress(text.encode("utf-8")))
    data[10] ^= 0xFF
    return bytes(data)


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(_corrupt_deflate('{"sample": "s-a"}\n' * 50), id="corrupt-deflate"),
        pytest.param(b'{"sample": "s-a"}\n', id="not-gzip"),
        pytest.param(gzip.compress(b'{"sample": "s-a"}\n' * 50)[:-12], id="truncated"),
    ],
)
def test_an_unreadable_file_names_the_path(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "answers.jsonl.gz"
    path.write_bytes(content)

    with pytest.raises(AnswersError, match=r"answers\.jsonl\.gz"):
        read_answers(path)
