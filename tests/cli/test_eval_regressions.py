"""``playbook eval --check-regressions NEW --against BASELINE`` (spec #281 ticket 08).

Driven through ``cli.main`` on hand-written metrics files; nothing runs an agent.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.cli import main
from coding_agent_playbook.evals.release_metrics_schema import validate_release_metrics
from tests.evals.release_metrics_files import metrics_file, sample_entry

if TYPE_CHECKING:
    from pathlib import Path


def _files(tmp_path: Path, old: float, new: float) -> tuple[Path, Path]:
    baseline = tmp_path / "old.json"
    baseline.write_text(json.dumps(metrics_file("9.9.8", {"s": sample_entry(old)})), "utf-8")
    current = tmp_path / "new.json"
    current.write_text(json.dumps(metrics_file("9.9.9", {"s": sample_entry(new)})), "utf-8")
    return current, baseline


def _check(current: Path, baseline: Path, *flags: str) -> int:
    return main(["eval", "--check-regressions", str(current), "--against", str(baseline), *flags])


def _read(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    validate_release_metrics(data)
    return data


def test_no_regression_exits_zero_and_prints_a_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    current, baseline = _files(tmp_path, 0.9, 0.9)
    assert _check(current, baseline) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "release 9.9.9 vs 9.9.8 on target 'claude-opus'"
    assert out.rstrip().endswith(": ok")


def test_an_unaccepted_regression_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    current, baseline = _files(tmp_path, 0.9, 0.7)
    assert _check(current, baseline) == 1
    assert "BLOCKED" in capsys.readouterr().out
    assert _read(current)["samples"]["s"]["vs_previous"]["status"] == "regression"


def test_an_accepted_regression_exits_zero_and_stores_its_reason(tmp_path: Path) -> None:
    current, baseline = _files(tmp_path, 0.9, 0.7)
    assert _check(current, baseline, "--accept", "s=stricter rubric") == 0
    data = _read(current)
    assert data["previous"] == "9.9.8"
    assert data["samples"]["s"]["vs_previous"]["accepted"] == "stricter rubric"
    assert _check(current, baseline) == 0  # the stored reason holds on a rerun


def test_json_format(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    current, baseline = _files(tmp_path, 0.9, 0.7)
    assert _check(current, baseline, "--format", "json") == 1
    data = json.loads(capsys.readouterr().out)
    assert (data["blocked"], data["regressions"]) == (True, 1)


@pytest.mark.parametrize(
    ("flags", "message"),
    [
        (["--accept", "s"], "SAMPLE=REASON"),
        (["--accept", "s= "], "SAMPLE=REASON"),
        (["--accept", "other=why"], "did not regress"),
    ],
)
def test_a_bad_accept_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flags: list[str], message: str
) -> None:
    current, baseline = _files(tmp_path, 0.9, 0.7)
    before = current.read_text(encoding="utf-8")
    assert _check(current, baseline, *flags) == 2
    assert message in capsys.readouterr().err
    assert current.read_text(encoding="utf-8") == before


def test_a_missing_against_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    current, _ = _files(tmp_path, 0.9, 0.9)
    assert main(["eval", "--check-regressions", str(current)]) == 2
    assert "--against" in capsys.readouterr().err


def test_against_without_check_regressions_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, baseline = _files(tmp_path, 0.9, 0.9)
    assert main(["eval", "--against", str(baseline)]) == 2
    assert "--check-regressions" in capsys.readouterr().err


def test_a_file_that_is_not_release_metrics_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    current, baseline = _files(tmp_path, 0.9, 0.9)
    baseline.write_text("{not json", encoding="utf-8")
    assert _check(current, baseline) == 2
    assert str(baseline) in capsys.readouterr().err


def test_check_regressions_with_run_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    current, baseline = _files(tmp_path, 0.9, 0.9)
    assert _check(current, baseline, "--run") == 2
    assert "drop --run" in capsys.readouterr().err
