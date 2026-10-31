"""Scoring bridge — grade an agent's output through the compiled sample.

:func:`score` grades the captured
:class:`~coding_agent_playbook.evals.run.harness_runner.Candidate` against the sample's
``setup/`` baseline (:class:`~coding_agent_playbook.evals.run.setup_baseline.SetupBaseline`)
into one :class:`~coding_agent_playbook.grading.types.EvaluationReport`. It sources the
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
  file (the ``setup/`` baseline's rows are measured once per sample); a file that
  cannot be read, parsed or measured, or is over 1 MB, is skipped;
* **execution** metrics (``needs_project``) run the candidate's test suite
  (:mod:`~coding_agent_playbook.evals.run.scoring_suite`: bounded, in an
  allowlisted environment, ``python -P`` with the session-record plugin
  :mod:`~coding_agent_playbook.grading.execution_metrics.suite_record_plugin`) —
  but **only when** an execution metric is actually referenced (``run_tests`` is
  *inferred*, not authored). A candidate suite that gives no result (it timed
  out, left no readable junit or coverage report, or its session disagrees with
  them) fails every execution
  check with its reason, and so does one whose result does not count because it
  hid tests from the pass rate: a setup/ test it no longer runs, a new skip,
  a non-strict xfail, a deselected or uncollected test, or no test that passed or failed
  (:func:`~coding_agent_playbook.evals.run.suite_integrity.suite_violation`). The
  sample cannot be scored (:class:`UnscorableSuiteError`) when this interpreter
  lacks pytest or pytest-cov
  (:func:`~coding_agent_playbook.evals.run.scoring_suite.require_suite_toolchain`),
  or when the ``setup/`` baseline's own suite gives no result;
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
``ctx.tree`` / ``ctx.baseline_tree`` directly. Both are temporary trees written
only after the trial's suite exited, immediately before grading: ``ctx.tree`` from
the paths those checks name, read into engine memory
(:func:`~coding_agent_playbook.evals.checks.files.freeze_file_inputs`) before the
suite ran, and ``ctx.baseline_tree`` from the sample's ``setup/`` snapshot. Why:
the suite runs agent code as the same user, which could put an edited file's
original bytes back, create a file the agent never wrote, or rewrite any file
the engine kept on disk while it ran. The static rows and the suite still read
the candidate tree itself.

The baseline is the sample's catalog ``setup/``, read into engine memory once
per sample before any agent code runs
(:mod:`~coding_agent_playbook.evals.run.setup_baseline`); scoring grades from that
copy and never reads the live catalog again, except to stop the sample
(:class:`~coding_agent_playbook.evals.run.setup_baseline.CatalogSetupChangedError`)
when the agent or its code modified it. A process that leaves its session (a
``setsid`` daemon) outlives the suite and is out of the engine's reach without
a sandbox.
"""

from __future__ import annotations

import tempfile
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.checks.files import freeze_file_inputs
from coding_agent_playbook.evals.run.scoring_suite import (
    check_suite_toolchain,
    open_suite_handle,
    static_metrics_of,
    suite_metrics_of,
    suite_rows,
    tree_static_rows,
)
from coding_agent_playbook.evals.run.setup_baseline import require_catalog_unchanged
from coding_agent_playbook.evals.run.suite_integrity import freeze_test_files, suite_violation
from coding_agent_playbook.grading.check import MeasurementSet
from coding_agent_playbook.grading.measuring import measured_metrics, referenced_metrics
from coding_agent_playbook.grading.types import EvalContext, EvaluationReport, MeasureSetup

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.evals.checks.files import FrozenFileInputs
    from coding_agent_playbook.evals.compile.compiler import VerdictSpec
    from coding_agent_playbook.evals.run.harness_runner import Candidate
    from coding_agent_playbook.evals.run.setup_baseline import SetupBaseline
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.grading.execution_metrics.project import ProjectHandle
    from coding_agent_playbook.grading.rubric import Rubric
    from coding_agent_playbook.grading.types import JudgeLike, Measurement

#: Label the candidate ``EvalContext`` carries — the artifact/rubric scope key
#: judged checks key their per-artifact measurements on.
_RUBRIC_LABEL = "rubric"


def score(
    sample: EvalSample,
    setup_baseline: SetupBaseline,
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
    metrics that rubric's checks reference over the candidate (the ``setup/``
    side comes from ``setup_baseline``), runs
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

    ``setup_baseline`` is ``sample``'s, measured once before any agent ran
    (:func:`~coding_agent_playbook.evals.run.setup_baseline.prepare_setup_baseline`);
    a baseline of another sample raises :exc:`ValueError`. After the candidate's
    suite the live catalog ``setup/`` must still match its snapshot, else
    :class:`~coding_agent_playbook.evals.run.setup_baseline.CatalogSetupChangedError`.

    Example::

        >>> score(sample, prepare_setup_baseline(sample), candidate).passed  # doctest: +SKIP
        True
    """
    from coding_agent_playbook.evals.sample import compile_eval_sample

    _require_baseline_of(sample, setup_baseline)
    compiled = compile_eval_sample(sample)
    rubric = compiled.per_trial
    fail_fast = fail_fast and compiled.short_circuit_safe
    graded = freeze_file_inputs(rubric.checks, candidate.tree)

    # Judge-backed metrics are NOT pre-measured here: a metric-backed check whose
    # metric ``needs_judge`` is JUDGED-tier and measures itself lazily at grade time
    # (``_MetricCheck._lazily_measure``), so the cost-tiered scheduler can
    # short-circuit it when a cheaper required gate already failed (no wasted judge
    # call). With no judge configured its rubric layer reports unavailable -> skipped.
    with ExitStack() as stack:
        measured = _measure(rubric, setup_baseline, candidate, stack)
        require_catalog_unchanged(setup_baseline)
        tree, baseline_tree = _graded_trees(graded, setup_baseline, stack)
        ctx = EvalContext(
            module=None,
            source="",
            label=_RUBRIC_LABEL,
            project=measured.project,
            tree=tree,
            baseline_tree=baseline_tree,
            artifact=_graded_artifact(candidate),
            judge_samples=judge_samples,
            judge=judge,
            candidate_measurements=measured.candidate,
            baseline_measurements=measured.baseline,
            measured_metrics=measured.measured_metrics,
            suite_failure=measured.suite_failure,
            suite_violation=measured.suite_violation,
        )
        ms = MeasurementSet(measured.candidate, measured.baseline or None)
        report = rubric.evaluate(ctx, ms, strict=False, fail_fast=fail_fast)

    apply_verdict(report, compiled.verdict_spec)
    return report


def _require_baseline_of(sample: EvalSample, setup_baseline: SetupBaseline) -> None:
    """Raise :exc:`ValueError` when ``setup_baseline`` was measured for another sample."""
    if setup_baseline.sample_id != sample.id:
        raise ValueError(
            f"score() got the setup/ baseline of {setup_baseline.sample_id!r} for sample "
            f"{sample.id!r}; expected prepare_setup_baseline() of the same sample"
        )


def _graded_trees(
    graded: FrozenFileInputs, setup_baseline: SetupBaseline, stack: ExitStack
) -> tuple[Path, Path]:
    """The file checks' ``(tree, baseline_tree)``, written now from memory; ``stack`` removes them.

    Called after every suite of the trial exited, so no agent code of this trial
    runs while they exist (an escaped ``setsid`` process aside).
    """
    work = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="playbook-eval-graded-")))
    return graded.write_tree(work / "tree"), setup_baseline.snapshot.write_tree(work / "setup")


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
# The measuring pass (grading/measuring.py), over the candidate tree
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Measured:
    """One trial's measuring pass: the rows, the candidate handle, the metrics it ran.

    ``suite_failure`` is why the candidate's suite gave no result, and
    ``suite_violation`` why the result it gave does not count; ``None`` when fine.
    """

    candidate: list[Measurement]
    baseline: list[Measurement]
    project: ProjectHandle | None
    measured_metrics: frozenset[str]
    suite_failure: str | None = None
    suite_violation: str | None = None


def _measure(
    rubric: Rubric, setup_baseline: SetupBaseline, candidate: Candidate, stack: ExitStack
) -> _Measured:
    """Measure the candidate with every metric ``rubric`` references, beside the setup/ rows.

    Static metrics run per ``*.py`` file; execution metrics run the candidate's
    suite, and only when one is referenced (``run_tests`` is inferred). The
    ``setup/`` rows were measured once per sample, before any agent ran. The
    candidate handle stays open on ``stack``: grading sees it as ``ctx.project``.
    """
    setup = MeasureSetup()
    candidate_rows = tree_static_rows(candidate.tree, static_metrics_of(rubric), setup)
    baseline_rows = list(setup_baseline.static_rows)
    promised = measured_metrics(referenced_metrics(rubric.checks, nested=True), setup)
    execution = suite_metrics_of(rubric)
    if not execution:
        return _Measured(candidate_rows, baseline_rows, project=None, measured_metrics=promised)
    check_suite_toolchain()
    tests = freeze_test_files(candidate.tree, candidate.changed_files)
    project = open_suite_handle(candidate.tree, stack)
    candidate_rows += suite_rows(project, execution, setup)
    baseline_rows += setup_baseline.suite_rows
    if project.no_result is not None:
        failure = project.no_result.reason
        return _Measured(candidate_rows, baseline_rows, project, promised, suite_failure=failure)
    violation = _suite_violation(project, setup_baseline, candidate, tests)
    return _Measured(candidate_rows, baseline_rows, project, promised, suite_violation=violation)


def _suite_violation(
    project: ProjectHandle,
    setup_baseline: SetupBaseline,
    candidate: Candidate,
    tests: Mapping[str, bytes],
) -> str | None:
    """Why the candidate's suite result does not count against the ``setup/`` baseline's, or ``None``.

    The candidate's handle already ran and gave a result (cached, so nothing
    reruns). ``tests`` holds the agent's changed test files as it left them, read
    before its suite ran; the ``setup/`` files are the sample's snapshot.
    """
    ours, theirs = project.run().record, setup_baseline.record
    if ours is None or theirs is None:
        # Unreachable while _project sets suite_record (a missing record is then
        # NoSuiteResultError); fail closed anyway: with no record, no rule can run.
        return "the suite left no session record to check"
    return suite_violation(
        ours,
        theirs,
        candidate_files=tests,
        setup_files=setup_baseline.snapshot.files,
        changed_files=candidate.changed_files,
    )
