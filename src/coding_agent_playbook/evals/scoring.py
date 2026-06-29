"""Scoring bridge — grade an agent's output through the compiled task.

:func:`score` turns a materialized :class:`~coding_agent_playbook.evals.runner.Baseline`
and the captured :class:`~coding_agent_playbook.evals.runner.Candidate` into one
:class:`~coding_agent_playbook.evaluators.types.EvaluationReport`. It sources the
checks from the task compiler (:mod:`coding_agent_playbook.evals._compile`):
the task's ``[gate]``/``[rubric]`` blocks compile (via
:func:`~coding_agent_playbook.evals.task.compile_eval_task`) into one per-trial
:class:`~coding_agent_playbook.evaluators.rubric.Rubric` carrying the two named
layer checks (``id="gate"`` / ``id="rubric"``), and a single
:meth:`Rubric.evaluate` folds them into the report. The per-trial **verdict** is
then *derived* from the layer results with skipped-neutral semantics
(:func:`~coding_agent_playbook.evals._compile.verdict_passed`) and written onto
``report.passed``.

The measurement layer still pre-computes the metric values the metric-backed
checks read, but now discovers which metrics to measure by **walking the compiled
check tree** (the gate/rubric layer checks → their composers → the metric leaves)
rather than from a flat ``[metrics]`` block:

* **static** metrics (``not needs_project``) are measured per candidate ``*.py``
  file (and over the pristine ``setup/`` snapshot for the baseline);
* **execution** metrics (``needs_project``) run a
  :class:`~coding_agent_playbook.evaluators.execution.project.ProjectHandle` over
  the candidate tree (and the snapshot for the baseline) — but **only when** an
  execution metric is actually referenced (``run_tests`` is *inferred*, not
  authored);
* **judge-backed** metrics (a
  :class:`~coding_agent_playbook.evaluators.checks.judge_metric.JudgeMetric`, or a
  rubric-group :class:`~coding_agent_playbook.evaluators.rubric.Rubric` containing
  ``JudgeCheck``\\ s) are measured only when a ``judge`` is configured; with no
  judge they are left unmeasured and their wrapping check / rubric layer reports
  ``available() is False`` and skips (the deterministic-only path).

The file checks (``[gate]`` predicates) ignore the
:class:`~coding_agent_playbook.evaluators.check.MeasurementSet` and read
``ctx.tree`` / ``ctx.baseline_tree`` directly.
"""

from __future__ import annotations

import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators import (
    EvalContext,
    EvaluationReport,
    Measurement,
    parse_module,
)
from coding_agent_playbook.evaluators.check import MeasurementSet, _MetricCheck
from coding_agent_playbook.evaluators.checks.compose import AllOf, AnyOf, Not
from coding_agent_playbook.evaluators.execution.project import ProjectHandle

if TYPE_CHECKING:
    from coding_agent_playbook.evals.runner import Baseline, Candidate
    from coding_agent_playbook.evals.task import EvalTask
    from coding_agent_playbook.evaluators import JudgeLike, ModuleModel
    from coding_agent_playbook.evaluators.check import Check
    from coding_agent_playbook.evaluators.metric import Metric

#: Directory names skipped when discovering candidate ``*.py`` source files.
_IGNORED_DIRS = frozenset(
    {"__pycache__", ".venv", "venv", "node_modules", "build", "dist", ".git", ".tox", ".mypy_cache"}
)

#: MODULE label the execution metrics key their suite-wide measurements on.
_SUITE_LABEL = "suite"

#: Label the candidate ``EvalContext`` carries — the artifact/rubric scope key
#: judged checks key their per-artifact measurements on.
_RUBRIC_LABEL = "rubric"


def score(
    task: EvalTask,
    baseline: Baseline,
    candidate: Candidate,
    *,
    judge: JudgeLike | None = None,
    samples: int = 1,
    fail_fast: bool = False,
) -> EvaluationReport:
    """Grade ``candidate`` for ``task`` into one report + derive the trial verdict.

    Compiles the task's ``[gate]``/``[rubric]`` blocks into one per-trial
    :class:`~coding_agent_playbook.evaluators.rubric.Rubric`
    (:func:`~coding_agent_playbook.evals.task.compile_eval_task`), pre-computes the
    metrics that rubric's checks reference over the candidate (and, for
    regression/execution, the pristine ``setup/`` baseline snapshot), runs
    :meth:`Rubric.evaluate`, then derives the per-trial verdict from the gate/rubric
    layer results (**skipped-neutral**) and writes it onto ``report.passed``.

    With ``judge=None`` (the default) the judged ``[rubric]`` layer reports
    unavailable and is skipped — the deterministic ``[gate]`` layer only, and the
    verdict is the gate's pass/fail (skipped rubric is neutral). With a ``judge``
    set, the rubric layer's ``JudgeCheck``\\ s score the candidate's captured diff
    and fold into the same report.

    ``fail_fast`` (default ``False``) toggles the scheduler's short-circuit: when
    ``True`` a lost deterministic gate skips the remaining costlier tiers, so a
    failing ``[gate]`` check spares the LLM judge. The runner passes ``True`` by
    default (cost-saving); ``--full-scoring`` flips it off.
    """
    from coding_agent_playbook.evals._compile import verdict_passed
    from coding_agent_playbook.evals.task import compile_eval_task

    compiled = compile_eval_task(task)
    rubric = compiled.per_trial

    metrics = _referenced_metrics(rubric.checks)
    static_metrics = [m for m in metrics if not m.needs_judge and not m.needs_project]
    exec_metrics = [m for m in metrics if not m.needs_judge and m.needs_project]

    candidate_measurements: list[Measurement] = []
    baseline_measurements: list[Measurement] = []

    if static_metrics:
        candidate_measurements += _static_measurements(candidate.tree, static_metrics)
        baseline_measurements += _static_measurements(baseline.setup_snapshot, static_metrics)

    # ``run_tests`` is inferred: execution metrics run iff one is referenced.
    run_exec = bool(exec_metrics)
    if run_exec:
        candidate_measurements += _execution_measurements(candidate.tree, exec_metrics)
        baseline_measurements += _execution_measurements(baseline.setup_snapshot, exec_metrics)

    # Judge-backed metrics are NOT pre-measured here: a metric-backed check whose
    # metric ``needs_judge`` is JUDGED-tier and measures itself lazily at grade time
    # (``_MetricCheck._lazily_measure``), so the cost-tiered scheduler can
    # short-circuit it when a cheaper required gate already failed (no wasted judge
    # call). With no judge configured its rubric layer reports unavailable -> skipped.
    with ExitStack() as stack:
        ctx = EvalContext(
            module=_availability_module(static_metrics),
            source="",
            label=_RUBRIC_LABEL,
            project=_availability_project(candidate.tree, stack) if run_exec else None,
            tree=candidate.tree,
            baseline_tree=baseline.setup_snapshot,
            artifact=candidate.diff,
            samples=samples,
            judge=judge,
            candidate_measurements=candidate_measurements,
            baseline_measurements=baseline_measurements,
        )
        ms = MeasurementSet(candidate_measurements, baseline_measurements or None)
        report = rubric.evaluate(ctx, ms, strict=False, fail_fast=fail_fast)

    # Derive the trial verdict from the gate/rubric layer results (skipped-neutral)
    # and make it the report's pass/fail. The gate/rubric CheckResults stay in
    # report.checks for reporting (and the aggregate ``over`` selector).
    report.passed = verdict_passed(report, compiled.verdict_ast)
    return report


# --------------------------------------------------------------------------- #
# Metric discovery — walk the compiled check tree
# --------------------------------------------------------------------------- #


def _referenced_metrics(checks: list[Check]) -> list[Metric]:
    """Every :class:`Metric` the compiled check tree references, deduped by name.

    Walks ``checks`` (the per-trial rubric's layer checks), descending the boolean
    composers (:class:`AllOf`/:class:`AnyOf`/:class:`Not` via their ``children``)
    and pulling the underlying
    :class:`~coding_agent_playbook.evaluators.metric.Metric` off every
    :class:`~coding_agent_playbook.evaluators.check._MetricCheck` leaf
    (``ThresholdCheck`` / ``NonRegressionCheck``). A metric that is itself a
    :class:`~coding_agent_playbook.evaluators.rubric.Rubric` (a rubric-group wrapped
    in a ``ThresholdCheck``) is collected as one judge-backed metric — its own
    ``JudgeCheck``\\ s are measured by its :meth:`Rubric.measure`, so we do not
    descend into them here. File / judge-only checks carry no metric and contribute
    nothing. Deduped by ``metric.name`` (a metric named by two checks measures once).
    """
    out: list[Metric] = []
    seen: set[str] = set()

    def _walk(check: Check) -> None:
        if isinstance(check, _MetricCheck):
            metric = check.metric
            if metric.name not in seen:
                seen.add(metric.name)
                out.append(metric)
            return
        if isinstance(check, (AllOf, AnyOf, Not)):
            for child in check.children:
                _walk(child)

    for check in checks:
        _walk(check)
    return out


# --------------------------------------------------------------------------- #
# Availability stand-ins — satisfy the metric checks' ctx-slot gate
# --------------------------------------------------------------------------- #


def _availability_module(static_metrics: list[Metric]) -> ModuleModel | None:
    """A parsed empty module so static metric checks report ``available``.

    A static metric's ``available(ctx)`` requires ``ctx.module is not None`` — the
    measurement-time gate. In the scoring bridge the static measurements are
    *already* computed (per candidate file), so the metric checks only need to
    grade the pre-built :class:`MeasurementSet`; this stand-in module flips their
    availability on without being measured. ``None`` when there are no static
    metric checks (nothing to satisfy).
    """
    if not static_metrics:
        return None
    return parse_module("", _RUBRIC_LABEL)


def _availability_project(tree: Path, stack: ExitStack) -> ProjectHandle:
    """A lazy candidate :class:`ProjectHandle` so execution checks report available.

    An execution metric's ``available(ctx)`` requires ``ctx.project is not None``.
    The handle is constructed lazily (it only shells out to ``pytest`` when
    :meth:`ProjectHandle.run` is called, which the *checks* never do — they grade
    the pre-built measurements), so this never re-runs the suite. The throwaway
    report dir is cleaned when the enclosing :class:`ExitStack` exits.
    """
    report_dir = Path(
        stack.enter_context(tempfile.TemporaryDirectory(prefix="playbook-eval-avail-"))
    )
    return ProjectHandle.create(tree, report_dir)


# --------------------------------------------------------------------------- #
# Static measurements (per source file)
# --------------------------------------------------------------------------- #


def _static_measurements(tree: Path, metrics: list[Metric]) -> list[Measurement]:
    """Run static metrics over every ``*.py`` file under ``tree``.

    The label is the tree-relative POSIX path so a candidate file matches its
    ``setup/`` baseline counterpart in the
    :class:`~coding_agent_playbook.evaluators.check.MeasurementSet` (same scope
    keys). Unparseable files are skipped.
    """
    measurements: list[Measurement] = []
    for path in _iter_py_files(tree):
        label = path.relative_to(tree).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover - unreadable file is rare
            continue
        try:
            module = parse_module(source, label)
        except SyntaxError:
            continue
        ctx = EvalContext(module=module, source=source, label=label)
        for metric in metrics:
            if metric.available(ctx):
                measurements.extend(metric.measure(ctx))
    return measurements


def _iter_py_files(root: Path) -> list[Path]:
    """Recurse ``root`` for ``*.py`` files, skipping dot/ignored dirs (sorted)."""
    out: list[Path] = []
    if not root.is_dir():
        return out
    for entry in sorted(root.iterdir()):
        if entry.is_dir():
            if entry.name.startswith(".") or entry.name in _IGNORED_DIRS:
                continue
            out.extend(_iter_py_files(entry))
        elif entry.is_file() and entry.suffix == ".py":
            out.append(entry)
    return out


# --------------------------------------------------------------------------- #
# Execution measurements (ProjectHandle over the tree)
# --------------------------------------------------------------------------- #


def _execution_measurements(tree: Path, metrics: list[Metric]) -> list[Measurement]:
    """Run the suite once under ``tree`` and collect execution measurements.

    Both execution metrics read the same :class:`ProjectHandle`, so the suite
    runs exactly once. The report dir is a throwaway temp dir. A suite that
    cannot be launched (no pytest in the target env) yields no measurements
    rather than failing the whole score — the deterministic ``[gate]`` layer
    still grades.
    """
    measurements: list[Measurement] = []
    with tempfile.TemporaryDirectory(prefix="playbook-eval-reports-") as report_dir:
        handle = ProjectHandle.create(tree, Path(report_dir))
        ctx = EvalContext(module=None, source="", label=_SUITE_LABEL, project=handle)
        try:
            for metric in metrics:
                if metric.available(ctx):
                    measurements.extend(metric.measure(ctx))
        except RuntimeError:
            return []
    return measurements
