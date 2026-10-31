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
  file (and over the sample's catalog ``setup/`` for the baseline); a file that
  cannot be read, parsed or measured, or is over 1 MB, is skipped;
* **execution** metrics (``needs_project``) run a
  :class:`~coding_agent_playbook.grading.execution_metrics.project.ProjectHandle` over
  the candidate tree (and a throwaway copy of ``setup/`` for the baseline) — but **only when** an
  execution metric is actually referenced (``run_tests`` is *inferred*, not
  authored). Each run stops after 300 s and runs with an allowlisted
  environment (:func:`~coding_agent_playbook.evals.run.scoring_suite.suite_env`:
  ``PATH``, ``HOME``, the locale, the temp dirs, the Python path and the Windows
  system variables), so no API key, token, agent socket or ``PYTEST_*`` option
  of the caller reaches agent code.
  The command is ``python -P -m pytest`` with the engine's session-record
  plugin (:mod:`~coding_agent_playbook.grading.execution_metrics.suite_record`),
  writing to a temp dir outside the suite's argv, so neither a planted
  ``pytest.py`` nor a ``conftest.py`` that rewrites the reports passes for pytest.
  A candidate suite that gives no result (it timed out, left no readable junit
  or coverage report, or its session disagrees with them) fails every execution
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
``ctx.tree`` / ``ctx.baseline_tree`` directly. ``ctx.tree`` holds the paths they
name as the agent left them, copied
(:func:`~coding_agent_playbook.evals.checks.files.freeze_file_inputs`) before the
suite runs: the suite runs agent code, which could otherwise put an edited
file's original bytes back, or create a file the agent never wrote. The static
rows and the suite still read the candidate tree itself.

The baseline is always the sample's catalog ``setup/``
(:attr:`~coding_agent_playbook.evals.sample.EvalSample.setup_dir`), never a copy
beside the agent's scratch repo: such a copy was the agent's to edit, which let
an edited file pass ``file_unchanged`` and a planted ``conftest.py`` break the
baseline suite. The baseline suite runs on a temporary copy of it, so the
suite's own writes (``.pyc`` files, caches) never touch the catalog.
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.checks.files import freeze_file_inputs
from coding_agent_playbook.evals.run.scoring_suite import (
    UnscorableSuiteError,
    check_suite_toolchain,
    open_suite_handle,
    static_metrics_of,
    suite_metrics_of,
    suite_rows,
    tree_static_rows,
)
from coding_agent_playbook.evals.run.suite_integrity import freeze_test_files, suite_violation
from coding_agent_playbook.grading.check import MeasurementSet
from coding_agent_playbook.grading.measuring import measured_metrics, referenced_metrics
from coding_agent_playbook.grading.types import EvalContext, EvaluationReport, MeasureSetup

if TYPE_CHECKING:
    from coding_agent_playbook.evals.compile.compiler import VerdictSpec
    from coding_agent_playbook.evals.run.harness_runner import Baseline, Candidate
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.grading.execution_metrics.project import ProjectHandle
    from coding_agent_playbook.grading.metric import Metric
    from coding_agent_playbook.grading.rubric import Rubric
    from coding_agent_playbook.grading.types import JudgeLike, Measurement

#: Label the candidate ``EvalContext`` carries — the artifact/rubric scope key
#: judged checks key their per-artifact measurements on.
_RUBRIC_LABEL = "rubric"


class BaselineSuiteError(UnscorableSuiteError):
    """The ``setup/`` baseline's own suite gave no result: the sample author's to fix."""


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
    regression/execution, the sample's catalog ``setup/``), runs
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

    ``baseline`` is the runner's materialized scratch repo; the reference tree
    scoring compares against is ``sample.setup_dir``, which the agent cannot reach.

    Example::

        >>> score(sample, baseline, capture(baseline.repo_root, baseline, log)).passed  # doctest: +SKIP
        True
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
        graded = _frozen_file_inputs(rubric, candidate, stack)
        measured = _measure(rubric, sample, candidate, stack)
        ctx = EvalContext(
            module=None,
            source="",
            label=_RUBRIC_LABEL,
            project=measured.project,
            tree=graded,
            baseline_tree=sample.setup_dir,
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


def _frozen_file_inputs(rubric: Rubric, candidate: Candidate, stack: ExitStack) -> Path:
    """A copy of the paths ``rubric``'s file checks name, made now; ``stack`` removes it.

    Called before the suite runs, for every sample (one code path; a few file
    copies), so the file checks grade the files as the agent left them.
    """
    work = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="playbook-eval-graded-")))
    return freeze_file_inputs(rubric.checks, candidate.tree, work / "tree")


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
    rubric: Rubric, sample: EvalSample, candidate: Candidate, stack: ExitStack
) -> _Measured:
    """Measure the candidate and ``sample``'s ``setup/`` with every metric ``rubric`` references.

    Static metrics run per ``*.py`` file; execution metrics run the suite once
    per tree, and only when one is referenced (``run_tests`` is inferred). The
    candidate handle stays open on ``stack``: grading sees it as ``ctx.project``.
    """
    setup = MeasureSetup()
    static = static_metrics_of(rubric)
    execution = suite_metrics_of(rubric)
    candidate_rows = tree_static_rows(candidate.tree, static, setup)
    baseline_rows = tree_static_rows(sample.setup_dir, static, setup)
    promised = measured_metrics(referenced_metrics(rubric.checks, nested=True), setup)
    if not execution:
        return _Measured(candidate_rows, baseline_rows, None, promised)
    check_suite_toolchain()
    tests = _frozen_test_files(candidate, stack)
    project = open_suite_handle(candidate.tree, stack)
    candidate_rows += suite_rows(project, execution, setup)
    baseline = open_suite_handle(_setup_copy(sample.setup_dir, stack), stack)
    baseline_rows += _baseline_suite_rows(sample, baseline, execution, setup)
    if project.no_result is not None:
        failure = project.no_result.reason
        return _Measured(candidate_rows, baseline_rows, project, promised, failure)
    violation = _suite_violation(project, baseline, sample, candidate, tests)
    return _Measured(candidate_rows, baseline_rows, project, promised, None, violation)


def _frozen_test_files(candidate: Candidate, stack: ExitStack) -> Path:
    """The agent's changed test files, copied before its suite runs; ``stack`` removes them."""
    work = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="playbook-eval-tests-")))
    return freeze_test_files(candidate.tree, candidate.changed_files, work / "tree")


def _baseline_suite_rows(
    sample: EvalSample, handle: ProjectHandle, metrics: list[Metric], setup: MeasureSetup
) -> list[Measurement]:
    """``sample``'s ``setup/`` suite measurements; :class:`BaselineSuiteError` when it gave none.

    ``handle`` runs over a throwaway copy of ``setup/`` (:func:`_setup_copy`). Why
    raise: ``setup/`` is the sample author's, so its failure is not the agent's
    to carry, and a regression check with no baseline row grades a "new" scope
    against unset bounds and passes. The message names the catalog ``setup/``,
    the tree the author edits, not the temporary copy the suite ran in.
    """
    rows = suite_rows(handle, metrics, setup)
    if handle.no_result is not None:
        raise BaselineSuiteError(
            f"the setup/ baseline suite of {sample.id} ({sample.setup_dir}) gave no result "
            f"({handle.no_result.reason}); a sample's setup/ suite must finish and write its reports"
        )
    return rows


def _suite_violation(
    project: ProjectHandle,
    baseline: ProjectHandle,
    sample: EvalSample,
    candidate: Candidate,
    tests: Path,
) -> str | None:
    """Why the candidate's suite result does not count against the ``setup/`` baseline's, or ``None``.

    Both handles already ran and gave a result (cached, so nothing reruns), and
    :func:`~coding_agent_playbook.evals.run.scoring_suite.open_suite_handle` asked each for a session record. ``tests`` holds the agent's
    test files as it left them (:func:`_frozen_test_files`).
    """
    ours, theirs = project.run().record, baseline.run().record
    if ours is None or theirs is None:
        return None
    return suite_violation(
        ours,
        theirs,
        candidate_tree=tests,
        setup_tree=sample.setup_dir,
        changed_files=candidate.changed_files,
    )


def _setup_copy(setup_dir: Path, stack: ExitStack) -> Path:
    """A throwaway copy of ``setup_dir`` (empty when it is missing); ``stack`` removes it.

    Why a copy: the suite writes ``.pyc`` files and caches into its rootdir, and the
    catalog ``setup/`` must stay as its edition digest pins it.
    """
    work = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="playbook-eval-setup-")))
    tree = work / "setup"
    if setup_dir.is_dir():
        shutil.copytree(setup_dir, tree, symlinks=True)
    else:
        tree.mkdir()
    return tree
