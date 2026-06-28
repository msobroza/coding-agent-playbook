"""Scoring bridge — grade an agent's output through the PR-M model (PR R1 §2).

:func:`score` turns a materialized :class:`~coding_agent_playbook.evals.runner.Baseline`
and the captured :class:`~coding_agent_playbook.evals.runner.Candidate` into one
:class:`~coding_agent_playbook.evaluators.types.EvaluationReport`. Every scoring
layer flows through the **single** :func:`~coding_agent_playbook.evaluators.grade.grade`
call (one model, one report):

* **``[metrics]``** — the static + execution evaluators selected by
  :func:`~coding_agent_playbook.evals.task.evaluators_for_task` for the task's
  ``[metrics]`` policy. Static evaluators run per candidate source file; execution
  evaluators run a :class:`~coding_agent_playbook.evaluators.execution.project.ProjectHandle`
  over the candidate tree, with the **baseline suite run on the pristine
  ``setup/`` snapshot** so non-regression compares against the untouched setup.

* **``[expected]``** — the four BOOL deterministic evaluators
  (:mod:`coding_agent_playbook.evaluators.expected`, R3) compiled by
  ``evaluators_for_task`` from the task's
  :class:`~coding_agent_playbook.evals.task.ExpectedOutcome`. Each reads the
  candidate tree (``ctx.tree``) — and the baseline ``setup/`` snapshot
  (``ctx.baseline_tree``) for ``file_unchanged`` — and yields one BOOL
  measurement with a must-be-true ``fail`` floor. Their un-registered instances
  are passed to :func:`grade` as ``extra_evaluators`` (the same mechanism the
  judged criteria use), so a failed check gates the report. This **replaces** the
  R1 interim inline compile that built BOOL findings outside ``grade``.

* **``[rubric]``** — one
  :class:`~coding_agent_playbook.evaluators.judged.JudgedCriterion` per criterion,
  included **only when a judge is configured** (the ``judge`` argument is not
  ``None``). Each scores the candidate's captured diff/transcript into a ``0-1``
  SCORE measurement (averaged over ``samples``) and is graded through the same
  :func:`grade` call. With no judge (the default) judged evaluators are skipped
  entirely: deterministic-only, the R1 behaviour preserved.

The un-registered ``[expected]`` + judged criterion instances are passed as
``extra_evaluators`` so :func:`grade` resolves each measurement's policy without a
registry lookup; the result is the single :class:`EvaluationReport`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators import (
    EvalContext,
    EvaluationReport,
    Measurement,
    MetricConfig,
    grade,
    parse_module,
)
from coding_agent_playbook.evaluators.execution.project import ProjectHandle
from coding_agent_playbook.evaluators.expected import _ExpectedEvaluator

if TYPE_CHECKING:
    from coding_agent_playbook.evals.runner import Baseline, Candidate
    from coding_agent_playbook.evals.task import EvalTask
    from coding_agent_playbook.evaluators import Evaluator, JudgeLike

#: Directory names skipped when discovering candidate ``*.py`` source files.
_IGNORED_DIRS = frozenset(
    {"__pycache__", ".venv", "venv", "node_modules", "build", "dist", ".git", ".tox", ".mypy_cache"}
)

#: MODULE label the execution evaluators key their suite-wide measurements on.
_SUITE_LABEL = "suite"

#: Label the judged criteria key their per-artifact measurements on (R2).
_RUBRIC_LABEL = "rubric"

#: Label the expected-outcome evaluators key their per-file context on (R3). The
#: BOOL evaluators key their *measurements* on their own path scope, not this.
_EXPECTED_LABEL = "expected"


def score(
    task: EvalTask,
    baseline: Baseline,
    candidate: Candidate,
    *,
    judge: JudgeLike | None = None,
    samples: int = 1,
) -> EvaluationReport:
    """Grade ``candidate`` for ``task`` into one report (deterministic + judged).

    The ``[metrics]`` static/execution measurements, the ``[expected]`` BOOL
    checks, and (with a ``judge``) the ``[rubric]`` judged criteria all feed the
    same :func:`grade` call. With ``judge=None`` (the default) only the
    deterministic ``[metrics]`` + ``[expected]`` layers run — the R1 behaviour,
    unchanged.
    """
    policy = task.metrics or MetricConfig()
    evaluators = _metric_evaluators_for_task(task, policy)

    static_evals = [ev for ev in evaluators if not ev.needs_project]
    exec_evals = [ev for ev in evaluators if ev.needs_project]

    candidate_measurements: list[Measurement] = []
    baseline_measurements: list[Measurement] = []
    extra_evaluators: dict[str, Evaluator] = {}

    if static_evals:
        candidate_measurements += _static_measurements(candidate.tree, static_evals)
        baseline_measurements += _static_measurements(baseline.setup_snapshot, static_evals)

    if exec_evals and policy.run_tests:
        candidate_measurements += _execution_measurements(candidate.tree, exec_evals)
        baseline_measurements += _execution_measurements(baseline.setup_snapshot, exec_evals)

    expected_evals = _expected_evaluators_for_task(task)
    if expected_evals:
        expected_measurements, expected_by_name = _expected_measurements(
            expected_evals, candidate, baseline
        )
        candidate_measurements += expected_measurements
        extra_evaluators.update(expected_by_name)

    if judge is not None:
        judged_evals = _judged_evaluators_for_task(task)
        if judged_evals:
            judged_measurements, judged_by_name = _judged_measurements(
                judged_evals, candidate, judge, samples
            )
            candidate_measurements += judged_measurements
            extra_evaluators.update(judged_by_name)

    return grade(
        candidate_measurements,
        baseline_measurements or None,
        policy,
        extra_evaluators=extra_evaluators,
    )


# --------------------------------------------------------------------------- #
# [metrics] evaluator selection
# --------------------------------------------------------------------------- #


def _metric_evaluators_for_task(task: EvalTask, policy: MetricConfig) -> list[Evaluator]:
    """The deterministic ``[metrics]`` evaluators selected by the task's config.

    Wraps :func:`~coding_agent_playbook.evals.task.evaluators_for_task` and keeps
    only the deterministic static/execution metrics — the judged ``[rubric]``
    criteria (handled by :func:`_judged_evaluators_for_task`) and the
    ``[expected]`` BOOL evaluators (handled by
    :func:`_expected_evaluators_for_task`) are filtered out.
    """
    from coding_agent_playbook.evals.task import evaluators_for_task

    return [
        ev
        for ev in evaluators_for_task(task, policy)
        if _is_deterministic(ev) and not isinstance(ev, _ExpectedEvaluator)
    ]


def _is_deterministic(evaluator: Evaluator) -> bool:
    from coding_agent_playbook.evaluators import Determinism

    return evaluator.determinism is Determinism.DETERMINISTIC


# --------------------------------------------------------------------------- #
# [expected] -> BOOL measurements (R3; routed through grade like every family)
# --------------------------------------------------------------------------- #


def _expected_evaluators_for_task(task: EvalTask) -> list[_ExpectedEvaluator]:
    """The task's ``[expected]`` BOOL evaluator instances (the expected family).

    Filters :func:`~coding_agent_playbook.evals.task.evaluators_for_task` down to
    the :class:`~coding_agent_playbook.evaluators.expected._ExpectedEvaluator`
    subclasses, the complement of :func:`_metric_evaluators_for_task`'s metric
    selection.
    """
    from coding_agent_playbook.evals.task import evaluators_for_task

    return [
        ev for ev in evaluators_for_task(task, task.metrics) if isinstance(ev, _ExpectedEvaluator)
    ]


def _expected_measurements(
    evaluators: list[_ExpectedEvaluator],
    candidate: Candidate,
    baseline: Baseline,
) -> tuple[list[Measurement], dict[str, Evaluator]]:
    """Run each ``[expected]`` evaluator over the candidate tree.

    Returns the BOOL measurements plus a ``name -> evaluator`` map (the
    un-registered ``expected:<kind>:<path>`` instances) so :func:`grade` can
    resolve each measurement's must-be-true policy without a registry lookup. The
    candidate tree is the post-agent scratch repo; the baseline tree is the
    pristine ``setup/`` snapshot (the ``file_unchanged`` reference).
    """
    ctx = EvalContext(
        module=None,
        source="",
        label=_EXPECTED_LABEL,
        tree=candidate.tree,
        baseline_tree=baseline.setup_snapshot,
    )
    measurements: list[Measurement] = []
    by_name: dict[str, Evaluator] = {}
    for evaluator in evaluators:
        if evaluator.available(ctx):
            measurements.extend(evaluator.evaluate(ctx))
            by_name[evaluator.name] = evaluator
    return measurements, by_name


# --------------------------------------------------------------------------- #
# [rubric] -> judged measurements (R2; only when a judge is configured)
# --------------------------------------------------------------------------- #


def _judged_evaluators_for_task(task: EvalTask) -> list[Evaluator]:
    """The task's ``[rubric]`` :class:`JudgedCriterion` instances (judged family).

    Filters :func:`~coding_agent_playbook.evals.task.evaluators_for_task` down to
    the JUDGED determinism — the complement of :func:`_metric_evaluators_for_task`'s
    deterministic selection.
    """
    from coding_agent_playbook.evals.task import evaluators_for_task
    from coding_agent_playbook.evaluators import Determinism

    return [
        ev for ev in evaluators_for_task(task, task.metrics) if ev.determinism is Determinism.JUDGED
    ]


def _judged_measurements(
    evaluators: list[Evaluator],
    candidate: Candidate,
    judge: JudgeLike,
    samples: int,
) -> tuple[list[Measurement], dict[str, Evaluator]]:
    """Score each judged criterion over the candidate diff into SCORE measurements.

    Returns the measurements plus a ``name -> evaluator`` map (the un-registered
    ``judged:<slug>`` instances) so :func:`grade` can resolve each measurement's
    policy without a registry lookup. The judged artifact is the candidate's
    captured ``git diff`` (the agent's change), keyed on a stable ``rubric`` label.
    """
    ctx = EvalContext(
        module=None,
        source="",
        label=_RUBRIC_LABEL,
        judge=judge,
        artifact=candidate.diff,
        samples=samples,
    )
    measurements: list[Measurement] = []
    by_name: dict[str, Evaluator] = {}
    for evaluator in evaluators:
        if evaluator.available(ctx):
            measurements.extend(evaluator.evaluate(ctx))
            by_name[evaluator.name] = evaluator
    return measurements, by_name


# --------------------------------------------------------------------------- #
# Static measurements (per source file)
# --------------------------------------------------------------------------- #


def _static_measurements(tree: Path, evaluators: list[Evaluator]) -> list[Measurement]:
    """Run static evaluators over every ``*.py`` file under ``tree``.

    The label is the tree-relative POSIX path so a candidate file matches its
    ``setup/`` baseline counterpart in :func:`grade` (same scope keys).
    Unparseable files are skipped.
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
        for evaluator in evaluators:
            if evaluator.available(ctx):
                measurements.extend(evaluator.evaluate(ctx))
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


def _execution_measurements(tree: Path, evaluators: list[Evaluator]) -> list[Measurement]:
    """Run the suite once under ``tree`` and collect execution measurements.

    Both execution evaluators read the same :class:`ProjectHandle`, so the suite
    runs exactly once. The report dir is a throwaway temp dir. A suite that cannot
    be launched (no pytest in the target env) yields no measurements rather than
    failing the whole score — the deterministic ``[expected]`` layer still grades.
    """
    measurements: list[Measurement] = []
    with tempfile.TemporaryDirectory(prefix="playbook-eval-reports-") as report_dir:
        handle = ProjectHandle.create(tree, Path(report_dir))
        ctx = EvalContext(module=None, source="", label=_SUITE_LABEL, project=handle)
        try:
            for evaluator in evaluators:
                if evaluator.available(ctx):
                    measurements.extend(evaluator.evaluate(ctx))
        except RuntimeError:
            return []
    return measurements
