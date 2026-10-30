"""``scripts/release_report.py``: the release metric bundle a release publishes (spec D5).

The fixture history is the release report's (``tests.evals.release_report_history``):
9.9.2 has no baseline, 9.9.3 compares both targets with 9.9.2, and 9.9.4 adds a
judge change on ``claude-opus``. Chart tests need matplotlib and skip without it;
the bundle without charts must build with no plotting library at all.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from coding_agent_playbook.evals.release_report_rows import AGREEMENT_COLUMNS, CSV_COLUMNS
from release_report import build_bundle, main
from tests.evals.release_report_history import (
    OPUS,
    QWEN,
    entry,
    file_of,
    write_file,
    write_history,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CHARTS = ("sample-deltas.png", "task-deltas.png", "task-trend.png")


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    write_history(tmp_path / "checkout" / "catalog" / "releases")
    return tmp_path / "checkout"


def _names(paths: list[Path]) -> list[str]:
    return sorted(path.name for path in paths)


def test_bundle_files_without_charts(checkout: Path, tmp_path: Path) -> None:
    out = tmp_path / "bundle"
    paths = build_bundle(checkout, "9.9.3", out, charts=False)
    expected = ["metrics-claude-opus.json", "metrics-history.csv", "metrics-opencode-qwen.json"]
    assert _names(paths) == [*expected, "report.md"]
    assert sorted(p.name for p in out.iterdir()) == _names(paths)


def test_the_bundle_is_flat(checkout: Path, tmp_path: Path) -> None:
    out = tmp_path / "bundle"
    build_bundle(checkout, "9.9.4", out, charts=False)
    assert all(path.is_file() for path in out.iterdir())


def test_metrics_files_are_byte_copies(checkout: Path, tmp_path: Path) -> None:
    out = tmp_path / "bundle"
    build_bundle(checkout, "9.9.4", out, charts=False)
    for target in (OPUS, QWEN):
        source = checkout / "catalog" / "releases" / "9.9.4" / "metrics" / f"{target}.json"
        assert (out / f"metrics-{target}.json").read_bytes() == source.read_bytes()


def test_report_and_history_csv(checkout: Path, tmp_path: Path) -> None:
    out = tmp_path / "bundle"
    build_bundle(checkout, "9.9.4", out, charts=False)
    assert (out / "report.md").read_text(encoding="utf-8").startswith("# Release metrics: 9.9.4")
    with (out / "metrics-history.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == list(CSV_COLUMNS)
    assert {row["release"] for row in rows} == {"9.9.2", "9.9.3", "9.9.4"}


def _add_995(checkout: Path) -> None:
    """A 9.9.5 of ``claude-opus`` after the 9.9.4 judge change, with no judge change itself."""
    data = file_of("9.9.5", OPUS, {"review/a": entry("review", 0.9, 3)}) | {"previous": "9.9.4"}
    write_file(checkout / "catalog" / "releases", data)


def test_judge_agreement_holds_only_this_release_rows(checkout: Path, tmp_path: Path) -> None:
    _add_995(checkout)
    out = tmp_path / "bundle"
    build_bundle(checkout, "9.9.4", out, charts=False)
    with (out / "judge-agreement.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert list(rows[0]) == list(AGREEMENT_COLUMNS)
    assert {row["release"] for row in rows} == {"9.9.4"}


def test_no_judge_agreement_after_the_judge_change(checkout: Path, tmp_path: Path) -> None:
    _add_995(checkout)
    out = tmp_path / "bundle"
    names = _names(build_bundle(checkout, "9.9.5", out, charts=False))
    assert "judge-agreement.csv" not in names
    assert not (out / "judge-agreement.csv").exists()


def test_unknown_version_exits_two(
    checkout: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--version", "9.9.9", "--out", str(tmp_path / "b"), "--checkout", str(checkout)]
    assert main([*argv, "--no-charts"]) == 2
    assert "9.9.9" in capsys.readouterr().err


def test_main_writes_the_bundle(checkout: Path, tmp_path: Path) -> None:
    out = tmp_path / "b"
    argv = ["--version", "9.9.3", "--out", str(out), "--checkout", str(checkout), "--no-charts"]
    assert main(argv) == 0
    assert (out / "report.md").is_file()


def test_bundle_builds_on_the_committed_catalog(tmp_path: Path) -> None:
    """The publish jobs run on today's catalog: 0.4.0's real files must bundle."""
    build_bundle(REPO_ROOT, "0.4.0", tmp_path, charts=False)
    for name in ("report.md", "metrics-history.csv", "metrics-opencode-qwen.json"):
        assert (tmp_path / name).is_file()


def test_charts_are_written(checkout: Path, tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    out = tmp_path / "bundle"
    paths = build_bundle(checkout, "9.9.4", out, charts=True)
    assert set(CHARTS) <= set(_names(paths))
    assert all((out / name).stat().st_size > 0 for name in CHARTS)


def test_no_baseline_writes_no_delta_charts(checkout: Path, tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    out = tmp_path / "bundle"
    names = _names(build_bundle(checkout, "9.9.2", out, charts=True))
    assert "task-trend.png" in names
    assert "task-deltas.png" not in names
    assert "sample-deltas.png" not in names
