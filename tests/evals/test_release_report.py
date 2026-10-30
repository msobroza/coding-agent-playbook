"""The release report (spec D4): deltas, verdicts, controls, trend, CSV and Markdown.

The history is hand-written (``release_report_history``): releases 9.9.2 to
9.9.4 of two targets, with a judge change at 9.9.4. The Markdown is pinned by a
golden file; regenerate it with
``python -c "from tests.evals.test_release_report import regenerate; regenerate()"``
after an intended rendering change, and review the diff.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coding_agent_playbook.evals.release_regression import check_regressions
from coding_agent_playbook.evals.release_report import (
    TRUNCATION_POINTER,
    ReleaseReportError,
    load_history,
    release_report,
)
from tests.evals.release_report_history import (
    NEW_JUDGE,
    OPUS,
    QWEN,
    entry,
    file_of,
    write_file,
    write_history,
)

GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "release_report" / "report.md"
TABLE_HEADER = (
    "| task | previous pass rate | pass rate | Δ pass rate | previous mean | mean | Δ mean "
    "| regressions | improvements | carried | rejudged | new |"
)
CSV_COLUMNS = [
    "release",
    "target",
    "task",
    "sample",
    "passes",
    "runs",
    "pass_rate",
    "mean_score",
    "delta_mean",
    "verdict",
    "measured_in_release",
    "rejudged_from_release",
    "judge_model",
    "inputs_digest",
    "setup_digest",
]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return write_history(tmp_path / "releases")


def _read(root: Path, release: str, target: str) -> dict[str, object]:
    data: dict[str, object] = json.loads(
        (root / release / "metrics" / f"{target}.json").read_text(encoding="utf-8")
    )
    return data


def test_load_history_orders_releases_by_semver(tmp_path: Path) -> None:
    for release in ("9.9.10", "9.9.2"):
        write_file(tmp_path, file_of(release, OPUS, {"review/a": entry("review", 0.9, 3)}))
    assert load_history(tmp_path).releases == ("9.9.2", "9.9.10")


def test_load_history_names_an_invalid_file(tmp_path: Path) -> None:
    path = write_file(tmp_path, file_of("9.9.2", OPUS, {}) | {"schema_version": 2})
    with pytest.raises(ReleaseReportError, match=str(path)):
        load_history(tmp_path)


def test_task_deltas_pool_passes_over_runs(root: Path) -> None:
    report = release_report(load_history(root), "9.9.4")
    review = next(t for t in report.tasks if t.target == OPUS and t.task == "review")
    # 9.9.3: 3 + 1 + 3 passes of 9 runs; 9.9.4: 3 + 2 + 3 of 9.
    assert review.previous_pass_rate == pytest.approx(7 / 9)
    assert review.pass_rate == pytest.approx(8 / 9)
    assert review.previous_mean == pytest.approx((0.92 + 0.5 + 0.95) / 3)
    assert review.mean == pytest.approx((0.88 + 0.7 + 0.95) / 3)
    assert review.counts["improvement"] == 1
    assert review.counts["rejudged"] == 1
    assert review.counts["ok"] == 1


def test_verdicts_match_check_regressions(root: Path) -> None:
    report = release_report(load_history(root), "9.9.4")
    for target in (OPUS, QWEN):
        expected = check_regressions(_read(root, "9.9.4", target), _read(root, "9.9.3", target))
        statuses = {v.sample_id: v.status for v in expected.samples}
        section = report.target(target)
        assert section.check is not None
        assert {v.sample_id: v.status for v in section.check.samples} == statuses


def test_a_target_without_a_baseline_says_so(root: Path) -> None:
    write_file(root, file_of("9.9.4", "codex-gpt", {"review/a": entry("review", 0.9, 3)}))
    report = release_report(load_history(root), "9.9.4")
    section = report.target("codex-gpt")
    assert section.baseline is None
    assert "codex-gpt: no baseline" in report.markdown()
    task = next(t for t in report.tasks if t.target == "codex-gpt")
    assert task.previous_pass_rate is None
    assert task.previous_mean is None


def test_a_dropped_target_is_ignored(root: Path) -> None:
    write_file(root, file_of("9.9.3", "codex-gpt", {"review/a": entry("review", 0.9, 3)}))
    report = release_report(load_history(root), "9.9.4")
    assert [section.target for section in report.targets] == [OPUS, QWEN]
    assert all(task.target != "codex-gpt" for task in report.tasks)
    assert all(point.target != "codex-gpt" for point in report.trend)
    assert "codex-gpt" not in report.markdown()


def test_controls_are_a_separate_table(root: Path) -> None:
    markdown = release_report(load_history(root), "9.9.4").markdown()
    controls = markdown.split("### Controls", 1)[1].split("###", 1)[0]
    assert "| review/a | 9.9.1 |" in controls
    tasks = markdown.split(TABLE_HEADER, 1)[1].split("###", 1)[0]
    assert "9.9.1" not in tasks


def test_the_trend_marks_the_judge_change(root: Path) -> None:
    report = release_report(load_history(root), "9.9.4")
    opus = [p for p in report.trend if p.target == OPUS and p.task == "review"]
    assert [p.release for p in opus] == ["9.9.2", "9.9.3", "9.9.4"]
    assert [p.judge_changed for p in opus] == [False, False, True]
    assert not any(p.judge_changed for p in report.trend if p.target == QWEN)


def test_csv_has_the_d4_columns_and_one_row_per_release_target_sample(root: Path) -> None:
    rows = release_report(load_history(root), "9.9.4").csv_rows()
    assert all(list(row) == CSV_COLUMNS for row in rows)
    assert len(rows) == 3 + 2 + 4 + 2 + 4 + 2
    first = next(r for r in rows if r["release"] == "9.9.2" and r["target"] == OPUS)
    assert first["verdict"] == ""
    assert first["delta_mean"] == ""
    rejudged = next(r for r in rows if r["release"] == "9.9.4" and r["sample"] == "review/a")
    assert rejudged["verdict"] == "rejudged"
    assert rejudged["rejudged_from_release"] == "9.9.3"
    assert rejudged["measured_in_release"] == "9.9.3"
    assert rejudged["judge_model"] == NEW_JUDGE
    assert rejudged["setup_digest"] == f"setup-9.9.4-{OPUS}"


def test_agreement_rows_join_the_old_judges(root: Path) -> None:
    rows = release_report(load_history(root), "9.9.4").agreement_rows()
    assert rows == [
        {
            "release": "9.9.4",
            "target": OPUS,
            "task": "review",
            "runs": "3",
            "pass_agreement": "1",
            "mean_abs_score_diff": "0.04",
            "old_judge": "judge-old, judge-older",
            "new_judge": NEW_JUDGE,
        }
    ]


def test_markdown_has_the_pinned_task_table_header(root: Path) -> None:
    assert TABLE_HEADER in release_report(load_history(root), "9.9.4").markdown()


def test_markdown_is_truncated_at_the_limit_with_a_pointer(root: Path) -> None:
    report = release_report(load_history(root), "9.9.4")
    full = report.markdown()
    cut = report.markdown(limit=len(full) // 2)
    assert len(cut) <= len(full) // 2
    assert cut.endswith(TRUNCATION_POINTER)
    kept = cut.removesuffix(TRUNCATION_POINTER)
    assert full.startswith(kept)
    assert full[len(kept) :].startswith("\n#")


def test_markdown_under_the_limit_is_whole(root: Path) -> None:
    full = release_report(load_history(root), "9.9.4").markdown()
    assert TRUNCATION_POINTER not in full


def test_markdown_matches_the_golden_file(root: Path) -> None:
    markdown = release_report(load_history(root), "9.9.4").markdown()
    assert markdown == GOLDEN.read_text(encoding="utf-8")


def test_an_unknown_version_names_the_versions_that_exist(root: Path) -> None:
    with pytest.raises(ReleaseReportError) as raised:
        release_report(load_history(root), "9.9.7")
    message = str(raised.value)
    assert str(root / "9.9.7" / "metrics") in message
    assert "9.9.2, 9.9.3, 9.9.4" in message


def regenerate() -> None:  # pragma: no cover - a maintainer's helper, not a test
    """Rewrite the golden file from the fixture history."""
    import tempfile

    with tempfile.TemporaryDirectory() as scratch:
        root = write_history(Path(scratch) / "releases")
        GOLDEN.write_text(release_report(load_history(root), "9.9.4").markdown(), "utf-8")
