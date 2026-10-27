"""The regression check between two release metrics files (spec #281 ticket 08).

Every file here is hand-written (``release_metrics_files``); nothing runs an agent.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from coding_agent_playbook.evals.release_metrics_schema import validate_release_metrics
from coding_agent_playbook.evals.release_regression import (
    RegressionCheck,
    RegressionCheckError,
    annotate_release_metrics,
    check_regressions,
    parse_acceptances,
)
from coding_agent_playbook.evals.release_regression_format import (
    format_regression_table,
    regression_check_to_dict,
)
from tests.evals.release_metrics_files import metrics_file, sample_entry

_OLD = "9.9.8"
_NEW = "9.9.9"


def _check(old: dict[str, Any], new: dict[str, Any], **accepted: str) -> RegressionCheck:
    return check_regressions(metrics_file(_NEW, new), metrics_file(_OLD, old), accepted=accepted)


def _status(check: RegressionCheck, sample_id: str) -> str:
    return next(v.status for v in check.samples if v.sample_id == sample_id)


def test_a_mean_drop_above_five_hundredths_regresses_and_blocks() -> None:
    check = _check({"s": sample_entry(0.9)}, {"s": sample_entry(0.8)})
    assert _status(check, "s") == "regression"
    assert check.samples[0].reasons == ("mean score drops 0.100",)
    assert check.blocked


def test_a_drop_of_exactly_five_hundredths_is_ok() -> None:
    check = _check({"s": sample_entry(0.8)}, {"s": sample_entry(0.75)})
    assert _status(check, "s") == "ok"
    assert not check.blocked


def test_passing_most_runs_before_and_failing_most_now_regresses() -> None:
    check = _check({"s": sample_entry(0.9, passes=3)}, {"s": sample_entry(0.9, passes=1)})
    assert _status(check, "s") == "regression"
    assert check.samples[0].reasons == (f"fails 2 of 3 runs on {_NEW}",)


def test_a_rise_above_the_threshold_is_an_improvement() -> None:
    check = _check({"s": sample_entry(0.5, passes=0)}, {"s": sample_entry(0.9)})
    assert _status(check, "s") == "improvement"
    assert not check.blocked


def test_a_changed_sample_digest_is_not_comparable_and_never_a_regression() -> None:
    old = {"s": sample_entry(0.9)}
    new = {"s": sample_entry(0.1, passes=0, digest="sample-digest-2")}
    check = _check(old, new)
    assert _status(check, "s") == "not_comparable"
    assert not check.blocked


def test_a_sample_without_a_baseline_entry_is_new() -> None:
    check = _check({}, {"s": sample_entry(0.1, passes=0)})
    assert _status(check, "s") == "new"
    assert not check.blocked


def test_a_sample_dropped_from_the_new_file_is_noted() -> None:
    check = _check({"s": sample_entry(0.9), "gone": sample_entry(0.9)}, {"s": sample_entry(0.9)})
    assert [v.sample_id for v in check.samples] == ["s"]
    assert any("gone" in note for note in check.notes)


def test_a_harness_version_change_is_noted_as_a_likely_cause() -> None:
    old = metrics_file(_OLD, {"s": sample_entry(0.9)}, harness_version="2.1.300")
    new = metrics_file(_NEW, {"s": sample_entry(0.9)}, harness_version="2.1.310")
    check = check_regressions(new, old)
    assert check.notes == (
        "harness version changed 2.1.300 -> 2.1.310: a likely cause of score changes",
    )


def test_a_cost_rise_above_a_quarter_is_a_warning_only() -> None:
    check = _check({"s": sample_entry(0.9, cost=0.10)}, {"s": sample_entry(0.9, cost=0.13)})
    verdict = check.samples[0]
    assert verdict.status == "ok"
    assert verdict.warnings == ("cost per run rises 30% (0.1 -> 0.13 USD)",)
    assert not check.blocked


def test_a_cost_rise_of_exactly_a_quarter_is_no_warning() -> None:
    check = _check({"s": sample_entry(0.9, cost=0.20)}, {"s": sample_entry(0.9, cost=0.25)})
    assert check.samples[0].warnings == ()


def test_tokens_stand_in_when_cost_is_null() -> None:
    old = {"s": sample_entry(0.9, tokens=1000.0)}
    new = {"s": sample_entry(0.9, tokens=1500.0, cost=None)}
    check = _check(old, new)
    assert check.samples[0].warnings == ("tokens per run rise 50% (1000 -> 1500)",)


def test_an_accepted_regression_does_not_block_and_keeps_its_reason() -> None:
    check = _check({"s": sample_entry(0.9)}, {"s": sample_entry(0.7)}, s="new rubric is stricter")
    verdict = check.samples[0]
    assert (verdict.status, verdict.accepted) == ("regression", "new rubric is stricter")
    assert not check.blocked


def test_accepting_a_sample_that_did_not_regress_is_refused() -> None:
    with pytest.raises(RegressionCheckError, match=r"'s'.*did not regress"):
        _check({"s": sample_entry(0.9)}, {"s": sample_entry(0.9)}, s="why")


def test_files_of_different_targets_are_refused() -> None:
    old = metrics_file(_OLD, {}, target="claude-opus")
    new = metrics_file(_NEW, {}, target="coder")
    with pytest.raises(RegressionCheckError, match=r"'coder'.*'claude-opus'"):
        check_regressions(new, old)


def test_annotating_stores_previous_vs_previous_and_counts() -> None:
    old = {"r": sample_entry(0.9), "a": sample_entry(0.9), "n": sample_entry(0.9)}
    new = {
        "r": sample_entry(0.7),
        "a": sample_entry(0.7),
        "n": sample_entry(0.9, digest="sample-digest-2"),
    }
    new_file = metrics_file(_NEW, new)
    check = check_regressions(new_file, metrics_file(_OLD, old), accepted={"a": "expected"})

    annotated: Any = annotate_release_metrics(new_file, check)

    validate_release_metrics(annotated)
    assert annotated["previous"] == _OLD
    assert annotated["samples"]["a"]["vs_previous"] == {
        "mean_score": 0.9,
        "delta": -0.2,
        "status": "regression",
        "reasons": ["mean score drops 0.200"],
        "accepted": "expected",
    }
    assert annotated["samples"]["n"]["vs_previous"]["status"] == "not_comparable"
    summary = annotated["summary"]
    assert (summary["regressions"], summary["accepted_regressions"]) == (2, 1)
    assert (summary["improvements"], summary["not_comparable"]) == (0, 1)
    assert new_file["previous"] is None  # the input is not changed


def test_a_reason_stored_in_the_new_file_stays_accepted_on_a_rerun() -> None:
    new_file = metrics_file(_NEW, {"s": sample_entry(0.7)})
    old_file = metrics_file(_OLD, {"s": sample_entry(0.9)})
    first = check_regressions(new_file, old_file, accepted={"s": "expected"})
    annotated = annotate_release_metrics(new_file, first)

    rerun = check_regressions(annotated, old_file)

    assert rerun.samples[0].accepted == "expected"
    assert not rerun.blocked


def test_the_table_names_each_sample_and_the_verdict() -> None:
    check = _check(
        {"s": sample_entry(0.9), "t": sample_entry(0.9)},
        {"s": sample_entry(0.7), "t": sample_entry(0.9)},
    )
    table = format_regression_table(check)
    assert table.splitlines()[0] == f"release {_NEW} vs {_OLD} on target 'claude-opus'"
    assert "REGRESSION: mean score drops 0.200" in table
    assert (
        table.splitlines()[-1]
        == "1 regression (0 accepted), 0 improvements, 0 not comparable, 0 carried: BLOCKED"
    )


def test_the_json_view_is_stable() -> None:
    check = _check({"s": sample_entry(0.9)}, {"s": sample_entry(0.7)}, s="expected")
    data = json.loads(json.dumps(regression_check_to_dict(check)))
    assert data["blocked"] is False
    assert (data["release"], data["previous"], data["target"]) == (_NEW, _OLD, "claude-opus")
    assert data["samples"][0]["accepted"] == "expected"


def _with_control(release: str, mean: float, *, edition: str = "v9.9.7") -> dict[str, Any]:
    control = sample_entry(mean, graded=edition)
    return metrics_file(release, {"s": sample_entry(0.9)}, controls={"s": control})


def test_a_control_that_moved_on_its_frozen_edition_is_noted_and_never_blocks() -> None:
    # Ticket 15: the edition did not change, so the model or the harness did.
    check = check_regressions(_with_control(_NEW, 0.5), _with_control(_OLD, 0.9))
    (note,) = (n for n in check.notes if n.startswith("control"))
    assert "'s' on frozen edition v9.9.7 moved (mean score drops 0.400" in note
    assert "the model or harness drifted" in note
    assert not check.blocked


def test_a_control_on_another_edition_is_not_compared() -> None:
    check = check_regressions(_with_control(_NEW, 0.5, edition="v9.9.8"), _with_control(_OLD, 0.9))
    assert not [n for n in check.notes if n.startswith("control")]


def test_parse_acceptances_strips_and_refuses_a_value_without_a_reason() -> None:
    assert parse_acceptances(["s = a reason "]) == {"s": "a reason"}
    with pytest.raises(RegressionCheckError, match="SAMPLE=REASON"):
        parse_acceptances(["s="])


# --------------------------------------------------------------------------- #
# Carried entries (#329 ticket 06)
# --------------------------------------------------------------------------- #


def _carried(mean: float, **extra: Any) -> dict[str, Any]:
    """An entry ``--carry-from`` copied from the baseline: it names where it was measured."""
    return sample_entry(mean, **extra) | {"measured_in": {"release": _OLD, "commit": None}}


def test_a_carried_entry_is_carried_with_the_previous_mean_and_no_delta() -> None:
    check = _check({"s": sample_entry(0.9)}, {"s": _carried(0.9)})
    verdict = check.samples[0]
    assert (verdict.status, verdict.previous_mean, verdict.delta) == ("carried", 0.9, 0.0)
    assert check.count("carried") == 1
    assert not check.blocked


def test_a_carried_entry_never_blocks_even_when_its_scores_would_regress() -> None:
    # Checked against another baseline than the one it was carried from.
    old = {"s": sample_entry(0.9, cost=0.1)}
    check = _check(old, {"s": _carried(0.5, passes=0, cost=0.5)})
    verdict = check.samples[0]
    assert (verdict.status, verdict.delta, verdict.reasons, verdict.warnings) == (
        "carried",
        0.0,
        (),
        (),
    )
    assert not check.blocked


def test_a_carried_entry_the_baseline_lacks_keeps_its_own_mean_as_the_previous() -> None:
    verdict = _check({}, {"s": _carried(0.8)}).samples[0]
    assert (verdict.status, verdict.previous_mean, verdict.delta) == ("carried", 0.8, 0.0)


def test_accepting_a_carried_sample_is_refused_as_did_not_regress() -> None:
    with pytest.raises(RegressionCheckError, match=r"'s'.*did not regress"):
        _check({"s": sample_entry(0.9)}, {"s": _carried(0.9)}, s="why")


def test_annotating_counts_the_rerun_and_the_carried_samples() -> None:
    old = {"c": sample_entry(0.9), "r": sample_entry(0.9)}
    new_file = metrics_file(_NEW, {"c": _carried(0.9), "r": sample_entry(0.9)})
    check = check_regressions(new_file, metrics_file(_OLD, old))

    annotated: Any = annotate_release_metrics(new_file, check)

    validate_release_metrics(annotated)
    assert annotated["samples"]["c"]["vs_previous"] == {
        "mean_score": 0.9,
        "delta": 0.0,
        "status": "carried",
    }
    assert (annotated["summary"]["rerun"], annotated["summary"]["carried"]) == (1, 1)


def test_a_full_record_counts_every_sample_as_rerun() -> None:
    new_file = metrics_file(_NEW, {"s": sample_entry(0.9)})
    check = check_regressions(new_file, metrics_file(_OLD, {"s": sample_entry(0.9)}))
    summary: Any = annotate_release_metrics(new_file, check)["summary"]
    assert (summary["rerun"], summary["carried"]) == (1, 0)


def test_the_table_and_the_json_view_count_the_carried_samples() -> None:
    check = _check({"s": sample_entry(0.9)}, {"s": _carried(0.9)})
    table = format_regression_table(check)
    assert "s       0.900     0.900  +0.000  carried" in table
    assert table.splitlines()[-1] == (
        "0 regressions (0 accepted), 0 improvements, 0 not comparable, 1 carried: ok"
    )
    assert regression_check_to_dict(check)["carried"] == 1
