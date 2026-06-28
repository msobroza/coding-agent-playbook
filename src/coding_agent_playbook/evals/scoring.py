"""Scoring bridge — grade an agent's output through the Metric/Check/Rubric model.

:func:`score` turns a materialized :class:`~coding_agent_playbook.evals.runner.Baseline`
and the captured :class:`~coding_agent_playbook.evals.runner.Candidate` into one
:class:`~coding_agent_playbook.evaluators.types.EvaluationReport`. T5a cuts this
over from the old ``grade(..., extra_evaluators=…)`` side-channel to the
:class:`~coding_agent_playbook.evaluators.rubric.Rubric` returned by
:func:`~coding_agent_playbook.evals.task.rubric_for_task`: the task's three eval
blocks become one ordered list of
:class:`~coding_agent_playbook.evaluators.check.Check`\\ es, and a single
:meth:`Rubric.evaluate` folds them into the report. The runner sets no ``Judge``
by default, so a ``[rubric]``'s :class:`~coding_agent_playbook.evaluators.checks.judged.JudgeCheck`\\ es
report ``available() is False`` and are skipped — deterministic-only, the R1
behaviour preserved.

The measurement layer mirrors the old ``score()`` exactly:

* **``[metrics]``** — the metric-backed checks (``ThresholdCheck`` /
  ``NonRegressionCheck``) read a
  :class:`~coding_agent_playbook.evaluators.check.MeasurementSet` we build up
  front. *Static* metrics are measured per candidate source file (and over the
  pristine ``setup/`` snapshot for the baseline); *execution* metrics run a
  :class:`~coding_agent_playbook.evaluators.execution.project.ProjectHandle` over
  the candidate tree (and the snapshot for the baseline) — **only when**
  ``task.metrics.run_tests``. So non-regression compares against the untouched
  setup, never the post-agent tree.

* **``[expected]``** — the four deterministic file checks
  (:mod:`coding_agent_playbook.evaluators.checks.files`) ignore the
  ``MeasurementSet`` and read the candidate tree (``ctx.tree``) — and the
  baseline ``setup/`` snapshot (``ctx.baseline_tree``) for ``file_unchanged`` —
  directly.

* **``[rubric]``** — the judged checks score the candidate's captured
  diff/transcript (``ctx.artifact``) into ``0-1`` SCORE leaves, but only when a
  judge is configured on the context; with no judge they skip.
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
    MetricConfig,
    parse_module,
)
from coding_agent_playbook.evaluators.check import MeasurementSet, _MetricCheck
from coding_agent_playbook.evaluators.execution.project import ProjectHandle

if TYPE_CHECKING:
    from coding_agent_playbook.evals.runner import Baseline, Candidate
    from coding_agent_playbook.evals.task import EvalTask
    from coding_agent_playbook.evaluators import JudgeLike, ModuleModel
    from coding_agent_playbook.evaluators.metric import Metric
    from coding_agent_playbook.evaluators.rubric import Rubric

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
    """Grade ``candidate`` for ``task`` into one report (deterministic + judged).

    Compiles the task's eval blocks into a
    :class:`~coding_agent_playbook.evaluators.rubric.Rubric`
    (:func:`~coding_agent_playbook.evals.task.rubric_for_task`), measures the
    metrics that rubric's metric-checks reference over the candidate (and, for
    regression/execution, the pristine ``setup/`` baseline snapshot), and runs
    :meth:`Rubric.evaluate`. With ``judge=None`` (the default) judged ``[rubric]``
    checks skip — the deterministic ``[metrics]`` + ``[expected]`` layers only,
    the R1 behaviour.

    ``fail_fast`` (default ``False``) toggles the scheduler's short-circuit: when
    ``True`` a lost deterministic gate skips the remaining costlier tiers, so a
    failing ``[expected]``/metric check spares the LLM judge. The runner passes
    ``True`` by default (cost-saving); ``--full-scoring`` flips it off.

    The single :class:`EvalContext` carries the slots every check family reads:
    the file checks read ``tree``/``baseline_tree``; the judged checks read
    ``artifact``/``samples``/``judge``; and the metric-backed checks read the
    pre-built :class:`MeasurementSet`. The metric checks gate their availability
    on the same ctx slot the underlying metric does (``ctx.module`` for static,
    ``ctx.project`` for execution), so the ctx is given a parsed empty
    ``module`` and — when execution metrics are in play — a lazy candidate
    :class:`ProjectHandle`; **neither is ever measured here** (the checks grade
    the pre-built measurements, never re-running ``measure``), they only satisfy
    the availability gate so the pre-computed scores actually grade.
    """
    from coding_agent_playbook.evals.task import rubric_for_task

    policy = task.metrics or MetricConfig()
    rubric = rubric_for_task(task, task.metrics)

    metrics = _metric_metrics(rubric)
    static_metrics = [m for m in metrics if not m.needs_project]
    exec_metrics = [m for m in metrics if m.needs_project]

    candidate_measurements: list[Measurement] = []
    baseline_measurements: list[Measurement] = []

    if static_metrics:
        candidate_measurements += _static_measurements(candidate.tree, static_metrics)
        baseline_measurements += _static_measurements(baseline.setup_snapshot, static_metrics)

    run_exec = bool(exec_metrics) and policy.run_tests
    if run_exec:
        candidate_measurements += _execution_measurements(candidate.tree, exec_metrics)
        baseline_measurements += _execution_measurements(baseline.setup_snapshot, exec_metrics)

    ms = MeasurementSet(candidate_measurements, baseline_measurements or None)
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
        return rubric.evaluate(ctx, ms, strict=policy.strict, fail_fast=fail_fast)


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
# Metric selection — the metrics the rubric's metric-checks reference
# --------------------------------------------------------------------------- #


def _metric_metrics(rubric: Rubric) -> list[Metric]:
    """The :class:`Metric` instances referenced by ``rubric``'s metric-checks.

    Walks the rubric's top-level checks and pulls the underlying
    :class:`~coding_agent_playbook.evaluators.metric.Metric` off each
    :class:`~coding_agent_playbook.evaluators.check._MetricCheck` (``ThresholdCheck``
    / ``NonRegressionCheck``). File and judged checks carry no metric, so they
    contribute nothing here — only the ``[metrics]`` block drives measurement.
    Deduped by ``metric.name`` to avoid measuring a metric twice when both a
    threshold and a regression policy name it.
    """
    metrics: list[Metric] = []
    seen: set[str] = set()
    for check in rubric.checks:
        if isinstance(check, _MetricCheck) and check.metric.name not in seen:
            seen.add(check.metric.name)
            metrics.append(check.metric)
    return metrics


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
    rather than failing the whole score — the deterministic ``[expected]`` layer
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
