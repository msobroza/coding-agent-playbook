"""Tests for the dormant eval-block → evaluator wiring (SPEC prM §D, M5).

Covers:
- parsing a top-level ``[metrics]`` table into ``EvalTask.metrics`` (a sibling
  of ``expected``/``rubric``);
- ``evaluators_for_task`` compiling ``[metrics]`` → static + execution
  evaluators and ``[rubric]`` → one ``JudgedCriterion`` per criterion;
- the compiled judged/execution evaluators being *dormant* (``available()``
  False without a judge/project) and the compiler never touching the v2
  runner/judge placeholders.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.evals.task import EvalTask, evaluators_for_task
from coding_agent_playbook.evaluators.judged import JudgedCriterion
from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    EvalContext,
    MetricConfig,
    RegressionPolicy,
)


def _task_with_metrics_and_rubric() -> EvalTask:
    data: dict[str, Any] = {
        "id": "demo-happy-path",
        "prompt_id": "demo",
        "description": "A demo task",
        "metrics": {
            "mode": "regression",
            "regression": {
                "cyclomatic_complexity": {"max_worsening": 0},
                "coverage": {"max_worsening": 0},
                "test_pass_rate": {"max_worsening": 0},
            },
        },
        "rubric": {
            "criteria": [
                "Findings prioritized correctly",
                "Each finding proposes a concrete fix",
            ],
            "weights": [0.5, 0.5],
        },
    }
    return EvalTask.from_dict(
        data,
        source_path=Path("/tmp/task.toml"),
        source_package="<test>",
    )


def _empty_ctx() -> EvalContext:
    return EvalContext(module=None, source="", label="output")


# --- EvalTask.metrics parsing -------------------------------------------------


def test_eval_task_metrics_defaults_none() -> None:
    task = EvalTask.from_dict(
        {"id": "t", "prompt_id": "p", "description": "d"},
        source_path=Path("/tmp/task.toml"),
        source_package="<test>",
    )
    assert task.metrics is None


def test_eval_task_parses_metrics_block() -> None:
    task = _task_with_metrics_and_rubric()
    assert isinstance(task.metrics, MetricConfig)
    assert task.metrics.mode == "regression"
    assert task.metrics.regression["coverage"] == RegressionPolicy(max_worsening=0.0)
    assert task.metrics.regression["cyclomatic_complexity"].max_worsening == 0.0


def test_eval_task_parses_metrics_thresholds_and_weights() -> None:
    data: dict[str, Any] = {
        "id": "t",
        "prompt_id": "p",
        "description": "d",
        "metrics": {
            "mode": "both",
            "thresholds": {"coverage": {"warn": 80, "fail": 60}},
            "weights": {"coverage": 1.0},
        },
    }
    task = EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")
    assert task.metrics is not None
    assert task.metrics.mode == "both"
    assert task.metrics.thresholds["coverage"] == AbsoluteThreshold(warn=80.0, fail=60.0)
    assert task.metrics.weights["coverage"] == pytest.approx(1.0)


def test_eval_task_metrics_is_sibling_of_expected_and_rubric() -> None:
    data: dict[str, Any] = {
        "id": "t",
        "prompt_id": "p",
        "description": "d",
        "expected": {"files_created": ["out.py"]},
        "rubric": {"criteria": ["A"]},
        "metrics": {"mode": "absolute"},
    }
    task = EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")
    assert task.expected is not None
    assert task.rubric is not None
    assert task.metrics is not None


def test_eval_task_metrics_rejects_non_table() -> None:
    data: dict[str, Any] = {"id": "t", "prompt_id": "p", "description": "d", "metrics": []}
    with pytest.raises(ValueError, match="metrics"):
        EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")


@pytest.mark.parametrize(
    ("block", "match"),
    [
        ({"thresholds": []}, "thresholds"),
        ({"thresholds": {"coverage": 5}}, "thresholds.coverage"),
        ({"regression": []}, "regression"),
        ({"regression": {"coverage": 5}}, "regression.coverage"),
        ({"weights": []}, "weights"),
    ],
)
def test_eval_task_metrics_rejects_malformed_subtables(block: dict[str, Any], match: str) -> None:
    data: dict[str, Any] = {
        "id": "t",
        "prompt_id": "p",
        "description": "d",
        "metrics": block,
    }
    with pytest.raises(ValueError, match=match):
        EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")


def test_eval_task_metrics_coerces_int_bounds_to_float() -> None:
    data: dict[str, Any] = {
        "id": "t",
        "prompt_id": "p",
        "description": "d",
        "metrics": {"thresholds": {"coverage": {"warn": 80, "fail": 60}}},
    }
    task = EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")
    assert task.metrics is not None
    warn = task.metrics.thresholds["coverage"].warn
    fail = task.metrics.thresholds["coverage"].fail
    assert isinstance(warn, float)
    assert isinstance(fail, float)


# --- evaluators_for_task ------------------------------------------------------


def test_evaluators_for_task_compiles_metrics_and_rubric() -> None:
    task = _task_with_metrics_and_rubric()
    evs = evaluators_for_task(task, task.metrics)
    names = {ev.name for ev in evs}
    # Static metric named in [metrics].regression is selected.
    assert "cyclomatic_complexity" in names
    # Execution evaluators named in [metrics] are selected too.
    assert "coverage" in names
    assert "test_pass_rate" in names
    # One JudgedCriterion per rubric criterion.
    judged = [ev for ev in evs if isinstance(ev, JudgedCriterion)]
    assert len(judged) == 2
    assert {ev.criterion for ev in judged} == {
        "Findings prioritized correctly",
        "Each finding proposes a concrete fix",
    }


def test_evaluators_for_task_assigns_rubric_weights() -> None:
    task = _task_with_metrics_and_rubric()
    evs = evaluators_for_task(task, task.metrics)
    judged = {ev.criterion: ev for ev in evs if isinstance(ev, JudgedCriterion)}
    assert judged["Findings prioritized correctly"].weight == pytest.approx(0.5)
    assert judged["Each finding proposes a concrete fix"].weight == pytest.approx(0.5)


def test_evaluators_for_task_uniform_weights_when_omitted() -> None:
    data: dict[str, Any] = {
        "id": "t",
        "prompt_id": "p",
        "description": "d",
        "rubric": {"criteria": ["A", "B", "C", "D"]},
    }
    task = EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")
    evs = evaluators_for_task(task, task.metrics)
    judged = [ev for ev in evs if isinstance(ev, JudgedCriterion)]
    assert len(judged) == 4
    assert all(ev.weight == pytest.approx(0.25) for ev in judged)


def test_evaluators_for_task_compiled_judged_and_execution_are_dormant() -> None:
    """With an empty ctx (no judge, no project) the judged + execution
    evaluators report unavailable, so the v1 runner would skip them. Static
    evaluators are unavailable too here only because there is no module."""
    task = _task_with_metrics_and_rubric()
    evs = evaluators_for_task(task, task.metrics)
    ctx = _empty_ctx()
    for ev in evs:
        if isinstance(ev, JudgedCriterion) or ev.name in {"coverage", "test_pass_rate"}:
            assert ev.available(ctx) is False


def test_evaluators_for_task_only_metrics() -> None:
    data: dict[str, Any] = {
        "id": "t",
        "prompt_id": "p",
        "description": "d",
        "metrics": {"mode": "regression", "regression": {"wmc": {"max_worsening": 0}}},
    }
    task = EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")
    evs = evaluators_for_task(task, task.metrics)
    names = {ev.name for ev in evs}
    assert "wmc" in names
    assert not any(isinstance(ev, JudgedCriterion) for ev in evs)


def test_evaluators_for_task_only_rubric() -> None:
    data: dict[str, Any] = {
        "id": "t",
        "prompt_id": "p",
        "description": "d",
        "rubric": {"criteria": ["A"], "weights": [1.0]},
    }
    task = EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")
    evs = evaluators_for_task(task, task.metrics)
    assert all(isinstance(ev, JudgedCriterion) for ev in evs)
    assert len(evs) == 1


def test_evaluators_for_task_empty_when_no_blocks() -> None:
    task = EvalTask.from_dict(
        {"id": "t", "prompt_id": "p", "description": "d"},
        source_path=Path("/tmp/task.toml"),
        source_package="<test>",
    )
    assert evaluators_for_task(task, task.metrics) == []


def test_evaluators_for_task_does_not_import_v2_runner() -> None:
    """Compiling blocks must not pull in (or call) the v2 runner/judge."""
    task = _task_with_metrics_and_rubric()
    # Drop any pre-imported runner module so we can prove the compiler does not
    # import it as a side effect.
    sys.modules.pop("coding_agent_playbook.evals.runner", None)
    evaluators_for_task(task, task.metrics)
    assert "coding_agent_playbook.evals.runner" not in sys.modules


def test_evaluators_for_task_dedupes_metric_named_in_multiple_blocks() -> None:
    """A metric named in both thresholds and regression compiles to exactly one
    evaluator, not two."""
    data: dict[str, Any] = {
        "id": "t",
        "prompt_id": "p",
        "description": "d",
        "metrics": {
            "thresholds": {"coverage": {"warn": 80}},
            "regression": {"coverage": {"max_worsening": 0}},
            "weights": {"coverage": 1.0},
        },
    }
    task = EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")
    evs = evaluators_for_task(task, task.metrics)
    assert [ev.name for ev in evs] == ["coverage"]


def test_evaluators_for_task_skips_unknown_metric_name() -> None:
    """An unknown evaluator name (flagged separately by the validator) is skipped
    by the compiler rather than raising."""
    data: dict[str, Any] = {
        "id": "t",
        "prompt_id": "p",
        "description": "d",
        "metrics": {
            "regression": {"wmc": {"max_worsening": 0}, "not_a_metric": {"max_worsening": 0}},
        },
    }
    task = EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")
    evs = evaluators_for_task(task, task.metrics)
    names = {ev.name for ev in evs}
    assert "wmc" in names
    assert "not_a_metric" not in names


def test_evaluators_for_task_does_not_call_judge_score() -> None:
    """Compilation only BUILDS evaluators; it must not invoke ``Judge.score``
    (the v2 placeholder raises ``NotImplementedError``). If it called the judge
    during compilation this would raise."""
    task = _task_with_metrics_and_rubric()
    # No judge supplied; building must succeed without scoring anything.
    evs = evaluators_for_task(task, task.metrics)
    assert any(isinstance(ev, JudgedCriterion) for ev in evs)


# --- evaluators_for_task: [expected] -> BOOL evaluators (R3) ------------------


def _task_with_expected() -> EvalTask:
    data: dict[str, Any] = {
        "id": "t",
        "prompt_id": "p",
        "description": "d",
        "expected": {
            "files_created": ["out.py", "helper.py"],
            "files_must_contain": [
                {"path": "out.py", "pattern": "def foo"},
                {"path": "out.py", "pattern": "def bar"},
            ],
            "files_unchanged": ["src/m.py"],
            "files_forbidden": ["__pycache__/"],
        },
    }
    return EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")


def test_evaluators_for_task_compiles_expected_into_bool_evaluators() -> None:
    from coding_agent_playbook.evaluators.expected import (
        FileContains,
        FileExists,
        FileForbidden,
        FileUnchanged,
    )

    evs = evaluators_for_task(_task_with_expected(), None)
    names = {ev.name for ev in evs}
    assert names == {
        "expected:file_exists:out.py",
        "expected:file_exists:helper.py",
        "expected:file_contains:out.py~/def foo/",
        "expected:file_contains:out.py~/def bar/",
        "expected:file_unchanged:src/m.py",
        "expected:file_forbidden:__pycache__/",
    }
    by_kind = {type(ev) for ev in evs}
    assert by_kind == {FileExists, FileContains, FileUnchanged, FileForbidden}


def test_evaluators_for_task_no_expected_emits_none() -> None:
    """A task with no [expected] block emits no expected:* evaluators."""
    evs = evaluators_for_task(_task_with_metrics_and_rubric(), None)
    assert not any(ev.name.startswith("expected:") for ev in evs)


def test_evaluators_for_task_expected_and_metrics_and_rubric_coexist() -> None:
    """All three families compile from one task into one evaluator list."""
    data: dict[str, Any] = {
        "id": "t",
        "prompt_id": "p",
        "description": "d",
        "metrics": {"regression": {"wmc": {"max_worsening": 0}}},
        "rubric": {"criteria": ["clarity"], "weights": [1.0]},
        "expected": {"files_created": ["out.py"]},
    }
    task = EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")
    evs = evaluators_for_task(task, task.metrics)
    names = {ev.name for ev in evs}
    assert "wmc" in names
    assert "judged:clarity" in names
    assert "expected:file_exists:out.py" in names
