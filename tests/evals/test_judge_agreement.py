"""How closely a new judge agrees with the old one on the same answers (spec D10)."""

from __future__ import annotations

from typing import Any

import pytest

from coding_agent_playbook.evals.judge_agreement import (
    AgreementRun,
    agreement_line,
    judge_change,
)
from coding_agent_playbook.evals.release_metrics_schema import (
    ReleaseMetricsError,
    validate_release_metrics,
)

_OLD = {"judge_model": "gpt-6-old", "judge_samples": 2}
_NEW = {"judge_model": "gpt-6-luna", "judge_samples": 2}


def _runs() -> list[AgreementRun]:
    """4 runs: one pass flip, score diffs 0.1, 0, 0.2, 0.1."""
    return [
        AgreementRun("refactor", True, True, 0.8, 0.9),
        AgreementRun("refactor", True, True, 0.7, 0.7),
        AgreementRun("explain", True, False, 0.6, 0.4),
        AgreementRun("explain", False, False, 0.2, 0.3),
    ]


def test_pass_agreement_and_mean_abs_diff_on_a_hand_computed_set() -> None:
    change = judge_change(_runs(), old=[_OLD], new=_NEW)

    assert change is not None
    assert change["runs"] == 4
    assert change["pass_agreement"] == 0.75
    assert change["mean_abs_score_diff"] == 0.1
    assert change["from"] == [_OLD]
    assert change["to"] == _NEW


def test_tasks_are_split() -> None:
    change = judge_change(_runs(), old=[_OLD], new=_NEW)

    assert change is not None
    assert change["tasks"] == {
        "explain": {"runs": 2, "pass_agreement": 0.5, "mean_abs_score_diff": 0.15},
        "refactor": {"runs": 2, "pass_agreement": 1.0, "mean_abs_score_diff": 0.05},
    }


def test_no_runs_gives_none() -> None:
    assert judge_change([], old=[_OLD], new=_NEW) is None


def test_distinct_old_judges_are_listed_once_in_a_stable_order() -> None:
    other = {"judge_model": "gpt-5-older", "judge_samples": 1}

    change = judge_change(_runs(), old=[_OLD, other, dict(_OLD)], new=_NEW)

    assert change is not None
    assert change["from"] == [other, _OLD]


def test_the_line_reads_as_specified() -> None:
    change = {
        "from": [_OLD],
        "to": _NEW,
        "runs": 96,
        "pass_agreement": 0.927083,
        "mean_abs_score_diff": 0.041234,
    }

    line = agreement_line(change)

    assert line == (
        "judge change: gpt-6-old -> gpt-6-luna: pass agreement 93% over 96 runs, mean |Δ| 0.04"
    )


def test_the_line_joins_several_old_judges() -> None:
    other = {"judge_model": "gpt-5-older"}
    change = judge_change(_runs(), old=[_OLD, other], new=_NEW)

    assert change is not None
    assert agreement_line(change).startswith("judge change: gpt-5-older, gpt-6-old -> gpt-6-luna:")


def _metrics(change: object) -> dict[str, Any]:
    target = {
        "name": "t",
        "harness": "fake",
        "harness_version": None,
        "model": "m",
        "reported_model": None,
        "label": "t",
        "endpoint": None,
        "price": None,
        "judge_model": None,
        "runs": 1,
    }
    summary = {
        "samples": 0,
        "runs": 0,
        "pass_rate": 0.0,
        "mean_score": None,
        "tokens": None,
        "cost_usd": None,
    }
    data: dict[str, Any] = {
        "schema_version": 1,
        "release": "9.9.3",
        "previous": None,
        "commit": None,
        "target": target,
        "summary": summary,
        "samples": {},
        "judge_change": change,
    }
    return data


def test_the_metrics_schema_accepts_a_judge_change() -> None:
    validate_release_metrics(_metrics(judge_change(_runs(), old=[_OLD], new=_NEW)))


@pytest.mark.parametrize(
    ("key", "value", "problem"),
    [
        ("from", {"judge_model": "x"}, "judge_change.from: expected list"),
        ("from", ["x"], "judge_change.from[0]: expected dict"),
        ("runs", "4", "judge_change.runs: expected int"),
        ("tasks", {"refactor": {"runs": 2}}, "judge_change.tasks.refactor.pass_agreement: missing"),
    ],
)
def test_the_metrics_schema_rejects_a_malformed_judge_change(
    key: str, value: object, problem: str
) -> None:
    change = judge_change(_runs(), old=[_OLD], new=_NEW)
    assert change is not None
    change[key] = value

    with pytest.raises(ReleaseMetricsError, match=problem.replace("[", r"\[").replace("]", r"\]")):
        validate_release_metrics(_metrics(change))
