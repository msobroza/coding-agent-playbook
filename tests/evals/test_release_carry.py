"""Which samples a carry-from record reruns, and how carried entries are copied (#329 ticket 05).

No runner and no CLI: baselines are hand-written files (``release_metrics_files``),
so each decision can be checked on its own.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.evals.release_carry import (
    CarryFromError,
    carried_entry,
    carry_plan_lines,
    load_baseline,
    merge_carried,
    plan_carry,
)
from coding_agent_playbook.evals.release_metrics import entries_summary
from coding_agent_playbook.evals.release_metrics_schema import (
    ReleaseMetricsError,
    validate_release_metrics,
)
from coding_agent_playbook.evals.setup_digest import SetupParts
from tests.evals.release_metrics_files import metrics_file, sample_entry

if TYPE_CHECKING:
    from pathlib import Path

_SETUP: dict[str, object] = SetupParts(
    "claude_code",
    "2.1.300",
    "claude-opus-5-5",
    None,
    None,
    3,
    None,
    None,
    None,
    None,
    True,
    True,
    "s1",
).as_dict()


def _baseline(
    samples: dict[str, dict[str, Any]],
    *,
    setup: dict[str, object] | None = _SETUP,
    release: str = "9.9.1",
    commit: str | None = "c1",
) -> dict[str, Any]:
    data = metrics_file(release, samples, commit=commit)
    if setup is not None:
        data |= {"setup_digest": "d1", "setup": dict(setup)}
    return data


def _two_samples() -> dict[str, Any]:
    return _baseline(
        {"a/one": sample_entry(0.5, inputs="in-a"), "b/two": sample_entry(1.0, inputs="in-b")}
    )


def test_unchanged_inputs_and_setup_carry_every_sample() -> None:
    plan = plan_carry(_two_samples(), setup=_SETUP, inputs={"a/one": "in-a", "b/two": "in-b"})
    assert plan.full_rerun_reason is None
    assert plan.rerun == {}
    assert set(plan.carried) == {"a/one", "b/two"}


def test_a_changed_inputs_digest_and_a_new_sample_rerun_with_their_reasons() -> None:
    inputs = {"a/one": "in-a-2", "b/two": "in-b", "c/new": "in-c"}
    plan = plan_carry(_two_samples(), setup=_SETUP, inputs=inputs)
    assert set(plan.rerun) == {"a/one", "c/new"}
    assert "inputs digest changed" in plan.rerun["a/one"]
    assert "new sample" in plan.rerun["c/new"]
    assert set(plan.carried) == {"b/two"}


def test_a_baseline_sample_gone_from_the_catalog_is_dropped() -> None:
    plan = plan_carry(_two_samples(), setup=_SETUP, inputs={"b/two": "in-b"})
    assert set(plan.carried) == {"b/two"}
    assert plan.rerun == {}


def test_a_differing_setup_reruns_everything_and_names_the_parts() -> None:
    setup = _SETUP | {"runs": 5, "scoring_digest": "s2"}
    plan = plan_carry(_two_samples(), setup=setup, inputs={"a/one": "in-a", "b/two": "in-b"})
    assert plan.full_rerun_reason is not None
    assert "runs" in plan.full_rerun_reason
    assert "scoring_digest" in plan.full_rerun_reason
    assert set(plan.rerun) == {"a/one", "b/two"}
    assert plan.carried == {}


def test_a_baseline_without_a_setup_digest_reruns_everything() -> None:
    baseline = _baseline({"a/one": sample_entry(0.5, inputs="in-a")}, setup=None)
    plan = plan_carry(baseline, setup=_SETUP, inputs={"a/one": "in-a"})
    assert plan.full_rerun_reason is not None
    assert "setup digest" in plan.full_rerun_reason
    assert plan.carried == {}


def test_a_baseline_entry_without_an_inputs_digest_reruns_everything() -> None:
    baseline = _baseline({"a/one": sample_entry(0.5), "b/two": sample_entry(1.0, inputs="in-b")})
    plan = plan_carry(baseline, setup=_SETUP, inputs={"a/one": "x", "b/two": "in-b"})
    assert plan.full_rerun_reason is not None
    assert "inputs digest" in plan.full_rerun_reason
    assert "'a/one'" in plan.full_rerun_reason
    assert set(plan.rerun) == {"a/one", "b/two"}


def test_a_carried_entry_drops_the_comparison_and_records_where_it_was_measured() -> None:
    entry = sample_entry(0.5, inputs="in-a") | {"vs_previous": {"status": "same"}, "accepted": "x"}
    carried = carried_entry(entry, release="9.9.1", commit="c1")
    assert "vs_previous" not in carried
    assert "accepted" not in carried
    assert carried["measured_in"] == {"release": "9.9.1", "commit": "c1"}
    assert carried["mean_score"] == 0.5
    assert "measured_in" not in entry  # the baseline entry itself is left as it was


def test_an_entry_carried_again_keeps_its_original_measured_in() -> None:
    first = carried_entry(sample_entry(0.5, inputs="i"), release="9.9.1", commit="c1")
    second = carried_entry(first, release="9.9.2", commit="c2")
    assert second["measured_in"] == {"release": "9.9.1", "commit": "c1"}


def test_entries_summary_pools_runs_and_averages_the_sample_means() -> None:
    entries = {
        "a": sample_entry(0.5, passes=1, runs=2),
        "b": sample_entry(1.0, passes=3, runs=3),
    }
    summary = entries_summary(entries)
    assert summary == {"samples": 2, "runs": 5, "pass_rate": 0.8, "mean_score": 0.75}


def test_entries_summary_of_nothing_has_no_mean_score() -> None:
    assert entries_summary({}) == {"samples": 0, "runs": 0, "pass_rate": 0.0, "mean_score": None}


def _fresh_file(samples: dict[str, dict[str, Any]]) -> dict[str, Any]:
    fresh = metrics_file("9.9.2", samples, commit="c2")
    fresh["target"]["reported_model"] = None
    fresh["summary"] |= {"tokens": 1200, "cost_usd": 0.5}
    return fresh


def test_merge_adds_the_carried_entries_and_rebuilds_the_summary_from_all_entries() -> None:
    inputs = {"a/one": "in-a-2", "b/two": "in-b"}
    plan = plan_carry(_two_samples(), setup=_SETUP, inputs=inputs)
    fresh = _fresh_file({"a/one": sample_entry(0.0, passes=0, runs=3, inputs="in-a-2")})
    merged = merge_carried(fresh, plan)
    validate_release_metrics(merged)
    assert set(merged["samples"]) == {"a/one", "b/two"}
    assert merged["samples"]["b/two"]["measured_in"] == {"release": "9.9.1", "commit": "c1"}
    summary = merged["summary"]
    assert (summary["samples"], summary["runs"], summary["rerun"], summary["carried"]) == (
        2,
        6,
        1,
        1,
    )
    assert summary["pass_rate"] == 0.5
    assert summary["mean_score"] == 0.5
    # Tokens and cost cover this record's fresh runs only.
    assert (summary["tokens"], summary["cost_usd"]) == (1200, 0.5)
    # No fresh run reported a model, so the baseline's (where the carried ones ran) stays.
    assert merged["target"]["reported_model"] == "claude-opus-5-5"


def test_validation_rejects_a_mistyped_measured_in_and_carry_counts() -> None:
    entry = sample_entry(0.5) | {"measured_in": {"release": 9, "commit": None}}
    data = metrics_file("9.9.2", {"a": entry})
    data["summary"] |= {"rerun": "1", "carried": 0}
    with pytest.raises(ReleaseMetricsError) as excinfo:
        validate_release_metrics(data)
    message = str(excinfo.value)
    assert "samples.a.measured_in.release" in message
    assert "summary.rerun" in message


def test_plan_lines_list_each_rerun_with_its_reason_and_the_carried_count() -> None:
    inputs = {"a/one": "in-a-2", "b/two": "in-b"}
    plan = plan_carry(_two_samples(), setup=_SETUP, inputs=inputs)
    lines = carry_plan_lines(plan, controls=["b/two"])
    text = "\n".join(lines)
    assert "1 rerun, 1 carried" in lines[0]
    assert "a/one: inputs digest changed" in text
    assert "b/two (edition control): edition controls always rerun" in text


def test_plan_lines_of_a_full_rerun_give_the_reason() -> None:
    plan = plan_carry(_two_samples(), setup=_SETUP | {"runs": 5}, inputs={"a/one": "in-a"})
    lines = carry_plan_lines(plan, controls=[])
    assert "every sample reruns" in lines[0]
    assert "runs" in lines[0]


def _write(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_baseline_reads_a_valid_file_for_the_same_target(tmp_path: Path) -> None:
    path = _write(tmp_path / "base.json", _two_samples())
    assert load_baseline(path, "claude-opus")["release"] == "9.9.1"


def test_load_baseline_refuses_another_target(tmp_path: Path) -> None:
    path = _write(tmp_path / "base.json", _two_samples())
    with pytest.raises(CarryFromError, match=r"'claude-opus'.*'other'"):
        load_baseline(path, "other")


@pytest.mark.parametrize("content", ["not json", None])
def test_load_baseline_refuses_a_missing_or_unreadable_file(
    tmp_path: Path, content: str | None
) -> None:
    path = tmp_path / "base.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with pytest.raises(CarryFromError, match=r"base\.json"):
        load_baseline(path, "claude-opus")


def test_load_baseline_refuses_an_invalid_file(tmp_path: Path) -> None:
    path = _write(tmp_path / "base.json", {"schema_version": 1})
    with pytest.raises(CarryFromError, match=r"--carry-from .*base\.json: release metrics file: "):
        load_baseline(path, "claude-opus")
