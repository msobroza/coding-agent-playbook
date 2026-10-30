"""Scoring bridge — grade an agent's output through the compiled sample.

:func:`score` turns a materialized :class:`~coding_agent_playbook.evals.run.harness_runner.Baseline`
and the captured :class:`~coding_agent_playbook.evals.run.harness_runner.Candidate` into one
:class:`~coding_agent_playbook.grading.types.EvaluationReport`. It sources the
checks from the sample compiler (:mod:`coding_agent_playbook.evals.compile.compiler`):
the sample's ``[gate]``/``[rubric]`` blocks compile (via
:func:`~coding_agent_playbook.evals.sample.compile_eval_sample`) into one per-trial
:class:`~coding_agent_playbook.grading.rubric.Rubric` carrying the two named
layer checks (``id="gate"`` / ``id="rubric"``), and a single
:meth:`Rubric.evaluate` folds them into the report. The per-trial **verdict** is
then *derived* from the layer results with skipped-neutral semantics
(:func:`~coding_agent_playbook.evals.compile.compiler.verdict_passed`) and written onto
``report.passed``.

The measurement layer pre-computes the metric values the metric-backed checks
read through the grading kernel's one measuring pass
(:mod:`coding_agent_playbook.grading.measuring`, shared with the metrics gate). It
discovers which metrics to measure by **walking the compiled check tree** (the
gate/rubric layer checks → their composers → the metric leaves) rather than from a
flat ``[metrics]`` block:

* **static** metrics (``not needs_project``) are measured per candidate ``*.py``
  file (and over the pristine ``setup/`` snapshot for the baseline); a file that
  cannot be read, parsed or measured, or is over 1 MB, is skipped;
* **execution** metrics (``needs_project``) run a
  :class:`~coding_agent_playbook.grading.execution_metrics.project.ProjectHandle` over
  the candidate tree (and the snapshot for the baseline) — but **only when** an
  execution metric is actually referenced (``run_tests`` is *inferred*, not
  authored);
* **judge-backed** metrics (a
  :class:`~coding_agent_playbook.grading.judge_metric.JudgeMetric`, or a
  rubric-group :class:`~coding_agent_playbook.grading.rubric.Rubric` containing
  ``JudgeCheck``\\ s) are measured only when a ``judge`` is configured; with no
  judge they are left unmeasured and their wrapping check / rubric layer reports
  ``available() is False`` and skips (the deterministic-only path).

The grading context names the metrics the pass ran (``measured_metrics``, nested
rubrics' leaves included), and a static or execution metric check is available
exactly when its metric is named there.

The file checks (``[gate]`` predicates) ignore the
:class:`~coding_agent_playbook.grading.check.MeasurementSet` and read
``ctx.tree`` / ``ctx.baseline_tree`` directly.
"""

from __future__ import annotations

import tempfile
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.grading.check import MeasurementSet
from coding_agent_playbook.grading.execution_metrics.project import ProjectHandle
from coding_agent_playbook.grading.measuring import (
    SourceMeter,
    measure_suite,
    measure_tree,
    measured_metrics,
    referenced_metrics,
)
from coding_agent_playbook.grading.types import EvalContext, EvaluationReport, MeasureSetup

if TYPE_CHECKING:
    from coding_agent_playbook.evals.compile.compiler import VerdictSpec
    from coding_agent_playbook.evals.run.harness_runner import Baseline, Candidate
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.grading.metric import Metric
    from coding_agent_playbook.grading.rubric import Rubric
    from coding_agent_playbook.grading.types import JudgeLike, Measurement

#: Label the candidate ``EvalContext`` carries — the artifact/rubric scope key
#: judged checks key their per-artifact measurements on.
_RUBRIC_LABEL = "rubric"


def score(
    sample: EvalSample,
    baseline: Baseline,
    candidate: Candidate,
    *,
    judge: JudgeLike | None = None,
    judge_samples: int = 1,
    fail_fast: bool = False,
) -> EvaluationReport:
    """Grade ``candidate`` for ``sample`` into one report + derive the trial verdict.

    Compiles the sample's ``[gate]``/``[rubric]`` blocks into one per-trial
    :class:`~coding_agent_playbook.grading.rubric.Rubric`
    (:func:`~coding_agent_playbook.evals.sample.compile_eval_sample`), pre-computes the
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
    default (cost-saving); ``--full-scoring`` flips it off. It is ignored for a
    sample whose verdict or aggregate the short-circuit could change (an ``or``
    verdict, a weighted verdict, an aggregate over a skippable layer — see
    :attr:`~coding_agent_playbook.evals.compile.compiler.CompiledSample.short_circuit_safe`).
    """
    from coding_agent_playbook.evals.sample import compile_eval_sample

    compiled = compile_eval_sample(sample)
    rubric = compiled.per_trial
    fail_fast = fail_fast and compiled.short_circuit_safe

    # Judge-backed metrics are NOT pre-measured here: a metric-backed check whose
    # metric ``needs_judge`` is JUDGED-tier and measures itself lazily at grade time
    # (``_MetricCheck._lazily_measure``), so the cost-tiered scheduler can
    # short-circuit it when a cheaper required gate already failed (no wasted judge
    # call). With no judge configured its rubric layer reports unavailable -> skipped.
    with ExitStack() as stack:
        measured = _measure(rubric, baseline, candidate, stack)
        ctx = EvalContext(
            module=None,
            source="",
            label=_RUBRIC_LABEL,
            project=measured.project,
            tree=candidate.tree,
            baseline_tree=baseline.setup_snapshot,
            artifact=_graded_artifact(candidate),
            judge_samples=judge_samples,
            judge=judge,
            candidate_measurements=measured.candidate,
            baseline_measurements=measured.baseline,
            measured_metrics=measured.measured_metrics,
        )
        ms = MeasurementSet(measured.candidate, measured.baseline or None)
        report = rubric.evaluate(ctx, ms, strict=False, fail_fast=fail_fast)

    apply_verdict(report, compiled.verdict_spec)
    return report


def apply_verdict(report: EvaluationReport, spec: VerdictSpec) -> None:
    """Derive the trial verdict from ``report``'s layers and make it the report's pass/fail.

    The gate/rubric CheckResults stay in ``report.checks`` for reporting (and the
    aggregate ``over`` selector). Two modes (C10): boolean (the ``[verdict].trial``
    expression, skipped-neutral over the layers' ``passed`` results) or weighted
    (a composite over the layers' 0-1 scores with renormalization for skipped
    layers). Shared with ``evals.rejudge``, which re-derives a stored run's verdict.

    Example::

        >>> apply_verdict(report, compile_eval_sample(sample).verdict_spec)  # doctest: +SKIP
    """
    from coding_agent_playbook.evals.compile.compiler import verdict_passed, weighted_verdict

    if spec.mode == "boolean":
        report.passed = verdict_passed(report, spec.ast)
        report.verdict_score = None
        return
    verdict_score, passed = weighted_verdict(report, spec)
    report.verdict_score = verdict_score
    report.passed = passed


def _graded_artifact(candidate: Candidate) -> str:
    """The text the artifact-side checks grade: the diff, else the transcript.

    An **edit** sample is graded on what the agent *did*, so its captured ``git
    diff`` is the artifact — unchanged, and the only case that existed before.

    A **review** sample is graded on what the agent *said*. Such a sample forbids
    edits (its ``[gate]`` is ``file_unchanged``), so a well-behaved agent leaves
    ``diff`` empty and its whole contribution lives in the transcript. Handing the
    judge that empty diff scored every review sample against nothing at all, so an
    empty diff falls back to the transcript. The shipped ``security-review-*`` and
    ``find-injected-vuln-*`` fixtures are all review samples.

    The discriminator is the diff rather than anything declared on the sample: a
    sample does not announce which kind it is, and an edit sample whose agent did
    nothing has no diff to grade either — its transcript is then strictly more
    informative than the empty string it would otherwise be graded on.
    """
    return candidate.diff if candidate.diff.strip() else candidate.transcript


# --------------------------------------------------------------------------- #
# The measuring pass (grading/measuring.py), over the candidate and setup/ trees
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Measured:
    """One trial's measuring pass: the rows, the candidate handle and the metrics it ran."""

    candidate: list[Measurement]
    baseline: list[Measurement]
    project: ProjectHandle | None
    measured_metrics: frozenset[str]


def _measure(
    rubric: Rubric, baseline: Baseline, candidate: Candidate, stack: ExitStack
) -> _Measured:
    """Measure the candidate and the ``setup/`` snapshot with every metric ``rubric`` references.

    Static metrics run per ``*.py`` file; execution metrics run the suite once
    per tree, and only when one is referenced (``run_tests`` is inferred). The
    candidate handle stays open on ``stack``: grading sees it as ``ctx.project``.
    """
    setup = MeasureSetup()
    referenced = referenced_metrics(rubric.checks)
    static = [m for m in referenced if not m.needs_judge and not m.needs_project]
    execution = [m for m in referenced if not m.needs_judge and m.needs_project]
    candidate_rows = _static_rows(candidate.tree, static, setup)
    baseline_rows = _static_rows(baseline.setup_snapshot, static, setup)
    project = _project(candidate.tree, stack) if execution else None
    if project is not None:
        candidate_rows += _suite_rows(project, execution, setup)
        baseline_rows += _suite_rows(_project(baseline.setup_snapshot, stack), execution, setup)
    promised = measured_metrics(referenced_metrics(rubric.checks, nested=True), setup)
    return _Measured(candidate_rows, baseline_rows, project, promised)


def _static_rows(tree: Path, metrics: list[Metric], setup: MeasureSetup) -> list[Measurement]:
    """``metrics`` over every ``*.py`` file of ``tree``; no walk when there is nothing to run.

    The label is the tree-relative POSIX path, so a candidate file matches its
    ``setup/`` baseline counterpart in the
    :class:`~coding_agent_playbook.grading.check.MeasurementSet` (same scope keys).
    """
    if not metrics:
        return []
    return list(measure_tree(tree, SourceMeter(metrics, setup)).measurements)


def _suite_rows(
    project: ProjectHandle, metrics: list[Metric], setup: MeasureSetup
) -> list[Measurement]:
    """The suite's measurements; one that cannot be launched (no pytest) yields none.

    The deterministic ``[gate]`` layer still grades rather than the whole score failing.
    """
    try:
        return measure_suite(project, metrics, setup)
    except RuntimeError:
        return []


def _project(tree: Path, stack: ExitStack) -> ProjectHandle:
    """A handle over ``tree`` whose throwaway report dir is removed when ``stack`` exits."""
    reports = stack.enter_context(tempfile.TemporaryDirectory(prefix="playbook-eval-reports-"))
    return ProjectHandle.create(tree, Path(reports))
