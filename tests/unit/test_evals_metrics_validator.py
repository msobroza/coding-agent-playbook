"""Tests for ``[metrics]``-block loading + validation (SPEC prM §D, M5).

The loader round-trips a ``task.toml`` carrying a ``[metrics]`` block into
``EvalTask.metrics``; the validator checks the block (known evaluator names,
valid mode, numeric bounds/deltas) while still enforcing the existing rubric
weight rules. Validation aggregates violations and never raises.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.loader import load_eval_task_from_dir
from coding_agent_playbook.evals.task import EvalTask, TaskSetup
from coding_agent_playbook.evals.validator import validate_tasks
from coding_agent_playbook.evaluators.types import MetricConfig
from coding_agent_playbook.types import Prompt, PromptFrontmatter

if TYPE_CHECKING:
    from pathlib import Path


def _make_prompt(prompt_id: str, eval_tasks: list[str] | None = None) -> Prompt:
    return Prompt(
        frontmatter=PromptFrontmatter(
            id=prompt_id,
            name=prompt_id.title(),
            description="prompt",
            slash=prompt_id,
            eval_tasks=eval_tasks or [],
        ),
        body="body\n",
        template_body="body\n",
        is_templated=False,
        source_path=None,
        source_package="<test>",
    )


def _write_task(task_dir: Path, body: str) -> Path:
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.toml").write_text(textwrap.dedent(body), encoding="utf-8")
    return task_dir


# --- loader -------------------------------------------------------------------


def test_loader_parses_metrics_block(tmp_path: Path) -> None:
    task_dir = _write_task(
        tmp_path / "with-metrics",
        """
        id = "with-metrics"
        prompt_id = "demo"
        description = "task with metrics"

        [metrics]
        mode = "regression"

        [metrics.regression]
        cyclomatic_complexity = { max_worsening = 0 }
        coverage = { max_worsening = 0 }
        test_pass_rate = { max_worsening = 0 }

        [rubric]
        criteria = ["Findings prioritized correctly", "Each finding proposes a fix"]
        weights = [0.5, 0.5]
        """,
    )
    task = load_eval_task_from_dir(task_dir, source_package="<test>")
    assert isinstance(task.metrics, MetricConfig)
    assert task.metrics.mode == "regression"
    assert set(task.metrics.regression) == {
        "cyclomatic_complexity",
        "coverage",
        "test_pass_rate",
    }
    assert task.rubric is not None
    assert task.rubric.weights == [0.5, 0.5]


# --- validator: helpers -------------------------------------------------------


def _task_with_metrics(task_dir: Path, metrics: MetricConfig | None) -> EvalTask:
    return EvalTask(
        id=task_dir.name,
        prompt_id="demo",
        description="d",
        source_path=task_dir / "task.toml",
        source_package="<test>",
        setup=TaskSetup(),
        metrics=metrics,
    )


# --- validator: positive ------------------------------------------------------


def test_validator_accepts_valid_metrics_block(tmp_path: Path) -> None:
    task_dir = tmp_path / "good"
    task_dir.mkdir()
    metrics = MetricConfig(
        mode="both",
        thresholds={},
        regression={},
        weights={},
    )
    from coding_agent_playbook.evaluators.types import (
        AbsoluteThreshold,
        RegressionPolicy,
    )

    metrics.regression = {"cyclomatic_complexity": RegressionPolicy(max_worsening=0.0)}
    metrics.thresholds = {"coverage": AbsoluteThreshold(warn=80.0)}
    metrics.weights = {"test_pass_rate": 1.0}

    prompt = _make_prompt("demo", eval_tasks=["good"])
    task = _task_with_metrics(task_dir, metrics)
    errors = validate_tasks([task], [prompt])
    assert [e for e in errors if "metric" in e.message.lower()] == []


def test_validator_accepts_execution_evaluator_names(tmp_path: Path) -> None:
    """coverage + test_pass_rate are execution metrics; they must be accepted
    as known names even though they are not in ``static_metrics()``."""
    task_dir = tmp_path / "exec"
    task_dir.mkdir()
    from coding_agent_playbook.evaluators.types import RegressionPolicy

    metrics = MetricConfig(
        regression={
            "coverage": RegressionPolicy(),
            "test_pass_rate": RegressionPolicy(),
        }
    )
    prompt = _make_prompt("demo", eval_tasks=["exec"])
    task = _task_with_metrics(task_dir, metrics)
    errors = validate_tasks([task], [prompt])
    assert [e for e in errors if "unknown evaluator" in e.message.lower()] == []


# --- validator: negative ------------------------------------------------------


def test_validator_rejects_unknown_evaluator_name(tmp_path: Path) -> None:
    task_dir = tmp_path / "bad-name"
    task_dir.mkdir()
    from coding_agent_playbook.evaluators.types import RegressionPolicy

    metrics = MetricConfig(regression={"not_a_real_metric": RegressionPolicy()})
    prompt = _make_prompt("demo", eval_tasks=["bad-name"])
    task = _task_with_metrics(task_dir, metrics)
    errors = validate_tasks([task], [prompt])
    assert any("not_a_real_metric" in e.message for e in errors)


def test_validator_rejects_bad_mode(tmp_path: Path) -> None:
    task_dir = tmp_path / "bad-mode"
    task_dir.mkdir()
    metrics = MetricConfig(mode="sideways")  # type: ignore[arg-type]
    prompt = _make_prompt("demo", eval_tasks=["bad-mode"])
    task = _task_with_metrics(task_dir, metrics)
    errors = validate_tasks([task], [prompt])
    assert any("mode" in e.message and "sideways" in e.message for e in errors)


def test_validator_rejects_non_numeric_threshold_bound(tmp_path: Path) -> None:
    task_dir = tmp_path / "bad-bound"
    task_dir.mkdir()
    from coding_agent_playbook.evaluators.types import AbsoluteThreshold

    # warn is a string -> not numeric.
    metrics = MetricConfig(thresholds={"coverage": AbsoluteThreshold(warn="lots")})  # type: ignore[arg-type]
    prompt = _make_prompt("demo", eval_tasks=["bad-bound"])
    task = _task_with_metrics(task_dir, metrics)
    errors = validate_tasks([task], [prompt])
    assert any("coverage" in e.message and "numeric" in e.message.lower() for e in errors)


def test_validator_rejects_non_numeric_regression_delta(tmp_path: Path) -> None:
    task_dir = tmp_path / "bad-delta"
    task_dir.mkdir()
    from coding_agent_playbook.evaluators.types import RegressionPolicy

    metrics = MetricConfig(
        regression={"coverage": RegressionPolicy(max_worsening="huge")}  # type: ignore[arg-type]
    )
    prompt = _make_prompt("demo", eval_tasks=["bad-delta"])
    task = _task_with_metrics(task_dir, metrics)
    errors = validate_tasks([task], [prompt])
    assert any("coverage" in e.message and "numeric" in e.message.lower() for e in errors)


def test_validator_rejects_non_numeric_weight(tmp_path: Path) -> None:
    task_dir = tmp_path / "bad-weight"
    task_dir.mkdir()
    metrics = MetricConfig(weights={"coverage": "heavy"})  # type: ignore[dict-item]
    prompt = _make_prompt("demo", eval_tasks=["bad-weight"])
    task = _task_with_metrics(task_dir, metrics)
    errors = validate_tasks([task], [prompt])
    assert any("coverage" in e.message and "numeric" in e.message.lower() for e in errors)


def test_validator_metrics_aggregates_with_other_errors(tmp_path: Path) -> None:
    """A metrics violation does not suppress the other rule checks; everything
    is aggregated."""
    task_dir = tmp_path / "multi"
    task_dir.mkdir()
    from coding_agent_playbook.evaluators.types import RegressionPolicy

    metrics = MetricConfig(regression={"nope": RegressionPolicy()})
    # prompt_id "ghost" does not exist -> a rule-3 error too.
    task = EvalTask(
        id="multi",
        prompt_id="ghost",
        description="d",
        source_path=task_dir / "task.toml",
        source_package="<test>",
        setup=TaskSetup(),
        metrics=metrics,
    )
    errors = validate_tasks([task], [])
    assert any("nope" in e.message for e in errors)
    assert any("prompt_id" in e.message for e in errors)


def test_validator_still_checks_rubric_weights_at_load_not_revalidated(tmp_path: Path) -> None:
    """The existing contract: rubric weights are validated at load time, not
    re-checked by the validator. Confirm adding [metrics] validation did not
    change that."""
    from coding_agent_playbook.evals.task import Rubric

    task_dir = tmp_path / "rubric-weights"
    task_dir.mkdir()
    prompt = _make_prompt("demo", eval_tasks=["rubric-weights"])
    task = _task_with_metrics(task_dir, None)
    task.rubric = Rubric(criteria=["A"], weights=[0.5])  # would not sum to 1.0
    errors = validate_tasks([task], [prompt])
    assert all("weight" not in e.message.lower() for e in errors)
