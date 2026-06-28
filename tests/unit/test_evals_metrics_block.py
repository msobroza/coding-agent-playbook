"""Tests for the eval-block → ``Check`` wiring (SPEC prM §D).

Covers:
- parsing a top-level ``[metrics]`` table into ``EvalTask.metrics`` (a sibling
  of ``expected``/``rubric``);
- ``rubric_for_task`` compiling ``[metrics]`` → metric-backed Checks, ``[rubric]``
  → one ``JudgeCheck`` per criterion, and ``[expected]`` → one file Check per
  entry, into a single :class:`~coding_agent_playbook.evaluators.rubric.Rubric`;
- the compiled judged Checks being *dormant* (``available()`` False without a
  judge) and the compiler never touching the runner/judge at build time.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.evals.task import EvalTask, rubric_for_task
from coding_agent_playbook.evaluators.check import _MetricCheck
from coding_agent_playbook.evaluators.checks.judged import JudgeCheck
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


def _judge_checks(task: EvalTask) -> list[JudgeCheck]:
    rubric = rubric_for_task(task, task.metrics)
    return [c for c in rubric.checks if isinstance(c, JudgeCheck)]


def _metric_names(task: EvalTask) -> set[str]:
    rubric = rubric_for_task(task, task.metrics)
    return {c.metric.name for c in rubric.checks if isinstance(c, _MetricCheck)}


def _check_ids(task: EvalTask) -> set[str]:
    rubric = rubric_for_task(task, task.metrics)
    return {c.id for c in rubric.checks}


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


# --- rubric_for_task: [metrics] + [rubric] -----------------------------------


def test_rubric_for_task_compiles_metrics_and_rubric() -> None:
    task = _task_with_metrics_and_rubric()
    names = _metric_names(task)
    # Static metric named in [metrics].regression is selected.
    assert "cyclomatic_complexity" in names
    # Execution metrics named in [metrics] are selected too.
    assert "coverage" in names
    assert "test_pass_rate" in names
    # One JudgeCheck per rubric criterion.
    judged = _judge_checks(task)
    assert len(judged) == 2
    assert {c.criterion for c in judged} == {
        "Findings prioritized correctly",
        "Each finding proposes a concrete fix",
    }


def test_rubric_for_task_assigns_rubric_weights() -> None:
    task = _task_with_metrics_and_rubric()
    judged = {c.criterion: c for c in _judge_checks(task)}
    assert judged["Findings prioritized correctly"].weight == pytest.approx(0.5)
    assert judged["Each finding proposes a concrete fix"].weight == pytest.approx(0.5)


def test_rubric_for_task_uniform_weights_when_omitted() -> None:
    data: dict[str, Any] = {
        "id": "t",
        "prompt_id": "p",
        "description": "d",
        "rubric": {"criteria": ["A", "B", "C", "D"]},
    }
    task = EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")
    judged = _judge_checks(task)
    assert len(judged) == 4
    assert all(c.weight == pytest.approx(0.25) for c in judged)


def test_rubric_for_task_compiled_judged_checks_are_dormant() -> None:
    """With an empty ctx (no judge) the judged Checks report unavailable, so the
    runner skips them."""
    task = _task_with_metrics_and_rubric()
    ctx = _empty_ctx()
    for check in _judge_checks(task):
        assert check.available(ctx) is False


def test_rubric_for_task_only_metrics() -> None:
    data: dict[str, Any] = {
        "id": "t",
        "prompt_id": "p",
        "description": "d",
        "metrics": {"mode": "regression", "regression": {"wmc": {"max_worsening": 0}}},
    }
    task = EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")
    assert "wmc" in _metric_names(task)
    assert _judge_checks(task) == []


def test_rubric_for_task_only_rubric() -> None:
    data: dict[str, Any] = {
        "id": "t",
        "prompt_id": "p",
        "description": "d",
        "rubric": {"criteria": ["A"], "weights": [1.0]},
    }
    task = EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")
    rubric = rubric_for_task(task, task.metrics)
    assert all(isinstance(c, JudgeCheck) for c in rubric.checks)
    assert len(rubric.checks) == 1


def test_rubric_for_task_empty_when_no_blocks() -> None:
    task = EvalTask.from_dict(
        {"id": "t", "prompt_id": "p", "description": "d"},
        source_path=Path("/tmp/task.toml"),
        source_package="<test>",
    )
    assert rubric_for_task(task, task.metrics).checks == []


def test_rubric_for_task_does_not_import_runner() -> None:
    """Compiling blocks must not pull in (or call) the runner."""
    task = _task_with_metrics_and_rubric()
    # Drop any pre-imported runner module so we can prove the compiler does not
    # import it as a side effect.
    sys.modules.pop("coding_agent_playbook.evals.runner", None)
    rubric_for_task(task, task.metrics)
    assert "coding_agent_playbook.evals.runner" not in sys.modules


def test_rubric_for_task_dedupes_metric_named_in_multiple_blocks() -> None:
    """A metric named in both thresholds and regression compiles to exactly one
    Check, not two."""
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
    rubric = rubric_for_task(task, task.metrics)
    metric_checks = [c for c in rubric.checks if isinstance(c, _MetricCheck)]
    assert [c.metric.name for c in metric_checks] == ["coverage"]


def test_rubric_for_task_skips_unknown_metric_name() -> None:
    """An unknown metric name (flagged separately by the validator) is skipped by
    the compiler rather than raising."""
    data: dict[str, Any] = {
        "id": "t",
        "prompt_id": "p",
        "description": "d",
        "metrics": {
            "regression": {"wmc": {"max_worsening": 0}, "not_a_metric": {"max_worsening": 0}},
        },
    }
    task = EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")
    names = _metric_names(task)
    assert "wmc" in names
    assert "not_a_metric" not in names


def test_rubric_for_task_does_not_call_judge_score() -> None:
    """Compilation only BUILDS Checks; it must not invoke the judge. With no judge
    supplied, building must succeed without scoring anything."""
    task = _task_with_metrics_and_rubric()
    assert _judge_checks(task)  # judged checks built, but never scored


# --- rubric_for_task: [expected] -> file Checks ------------------------------


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


def test_rubric_for_task_compiles_expected_into_file_checks() -> None:
    from coding_agent_playbook.evaluators.checks.files import (
        FileContainsCheck,
        FileExistsCheck,
        FileForbiddenCheck,
        FileUnchangedCheck,
    )

    rubric = rubric_for_task(_task_with_expected(), None)
    file_checks = [
        c
        for c in rubric.checks
        if isinstance(
            c, (FileExistsCheck, FileContainsCheck, FileUnchangedCheck, FileForbiddenCheck)
        )
    ]
    ids = {c.id for c in file_checks}
    assert ids == {
        "file_exists:out.py",
        "file_exists:helper.py",
        "file_contains:out.py~/def foo/",
        "file_contains:out.py~/def bar/",
        "file_unchanged:src/m.py",
        "file_forbidden:__pycache__/",
    }
    by_kind = {type(c) for c in file_checks}
    assert by_kind == {
        FileExistsCheck,
        FileContainsCheck,
        FileUnchangedCheck,
        FileForbiddenCheck,
    }


def test_rubric_for_task_no_expected_emits_no_file_checks() -> None:
    """A task with no [expected] block emits no file:* Checks."""
    ids = _check_ids(_task_with_metrics_and_rubric())
    assert not any(i.startswith("file_") for i in ids)


def test_rubric_for_task_expected_and_metrics_and_rubric_coexist() -> None:
    """All three families compile from one task into one Rubric."""
    data: dict[str, Any] = {
        "id": "t",
        "prompt_id": "p",
        "description": "d",
        "metrics": {"regression": {"wmc": {"max_worsening": 0}}},
        "rubric": {"criteria": ["clarity"], "weights": [1.0]},
        "expected": {"files_created": ["out.py"]},
    }
    task = EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")
    ids = _check_ids(task)
    assert "nonreg:wmc" in ids
    assert "judge:clarity" in ids
    assert "file_exists:out.py" in ids


# --- rubric_for_task: [rubric] ref = "<name>" (named-rubric registry) ---------


def test_rubric_for_task_splices_ref_rubric_judge_checks() -> None:
    """A registered ``ref`` splices the named rubric's JudgeChecks into the task's
    Rubric; the task Rubric's name stays ``task.id``."""
    from coding_agent_playbook.evaluators import rubrics as rubrics_mod
    from coding_agent_playbook.evaluators.rubric import Rubric

    @rubrics_mod.register_rubric("_ref_only")
    class _Ref(Rubric):
        CRITERIA = (("ref crit one", 1.0), ("ref crit two", 1.0))

    data: dict[str, Any] = {
        "id": "task-with-ref",
        "prompt_id": "p",
        "description": "d",
        "rubric": {"ref": "_ref_only"},
    }
    task = EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")
    try:
        rubric = rubric_for_task(task, task.metrics)
        assert rubric.name == "task-with-ref"
        judged = [c for c in rubric.checks if isinstance(c, JudgeCheck)]
        assert {c.criterion for c in judged} == {"ref crit one", "ref crit two"}
        # define() normalizes the two equal weights to 0.5 / 0.5.
        assert all(c.weight == pytest.approx(0.5) for c in judged)
    finally:
        rubrics_mod._RUBRIC_REGISTRY.pop("_ref_only", None)


def test_rubric_for_task_ref_coexists_with_expected_and_metrics() -> None:
    """``ref`` + ``[expected]`` + ``[metrics]`` together: the ref's JudgeChecks
    land ALONGSIDE the file + metric Checks in one Rubric."""
    from coding_agent_playbook.evaluators import rubrics as rubrics_mod
    from coding_agent_playbook.evaluators.rubric import Rubric

    @rubrics_mod.register_rubric("_ref_plus")
    class _Ref(Rubric):
        CRITERIA = (("ref criterion", 1.0),)

    data: dict[str, Any] = {
        "id": "t",
        "prompt_id": "p",
        "description": "d",
        "metrics": {"regression": {"wmc": {"max_worsening": 0}}},
        "rubric": {"ref": "_ref_plus"},
        "expected": {"files_created": ["out.py"]},
    }
    task = EvalTask.from_dict(data, source_path=Path("/tmp/task.toml"), source_package="<test>")
    try:
        ids = _check_ids(task)
        assert "nonreg:wmc" in ids  # [metrics]
        assert "judge:ref-criterion" in ids  # ref rubric
        assert "file_exists:out.py" in ids  # [expected]
    finally:
        rubrics_mod._RUBRIC_REGISTRY.pop("_ref_plus", None)
