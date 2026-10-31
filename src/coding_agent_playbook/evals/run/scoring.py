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
  environment (:func:`_suite_env`: ``PATH``, ``HOME``, the locale, the temp dirs,
  the Python path and the Windows system variables), so no API key, token,
  agent socket or ``PYTEST_*`` option of the caller reaches agent code.
  A candidate suite that gives no result (it timed out, or left no readable
  junit or coverage report) fails every execution check with its reason. The
  sample cannot be scored (:class:`UnscorableSuiteError`) when this interpreter
  lacks pytest or pytest-cov (:func:`require_suite_toolchain`), or when the
  ``setup/`` baseline's own suite gives no result;
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

import importlib.util
import os
import shutil
import sys
import tempfile
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evals.checks.files import freeze_file_inputs
from coding_agent_playbook.exit_two import ExitTwoError
from coding_agent_playbook.grading.check import MeasurementSet
from coding_agent_playbook.grading.execution_metrics.project import (
    NoSuiteResultError,
    ProjectHandle,
)
from coding_agent_playbook.grading.measuring import (
    SourceMeter,
    measure_suite,
    measure_tree,
    measured_metrics,
    referenced_metrics,
)
from coding_agent_playbook.grading.types import EvalContext, EvaluationReport, MeasureSetup

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.evals.compile.compiler import VerdictSpec
    from coding_agent_playbook.evals.run.harness_runner import Baseline, Candidate
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.grading.metric import Metric
    from coding_agent_playbook.grading.rubric import Rubric
    from coding_agent_playbook.grading.types import JudgeLike, Measurement

#: Label the candidate ``EvalContext`` carries — the artifact/rubric scope key
#: judged checks key their per-artifact measurements on.
_RUBRIC_LABEL = "rubric"

#: Bound on one scoring suite run, in seconds. Why: an agent's test, or the code it
#: tests, can loop forever, and the run had no timeout, so one trial stalled a whole
#: ``eval --record``. The shipped samples' suites finish in seconds.
_SUITE_TIMEOUT_S: Final = 300.0

#: The caller's variables the scoring suite keeps (compared upper-cased, as Windows
#: names are case-insensitive); every other one is dropped. Why an allowlist: the
#: suite runs agent-written code, and the engine's environment holds API keys,
#: endpoint tokens, ``GITHUB_TOKEN`` and ``SSH_AUTH_SOCK``. ``PYTHONPATH`` and
#: ``PYTHONHOME`` stay because :func:`require_suite_toolchain`'s in-process
#: ``find_spec`` saw them: without them the suite could miss a toolchain the check
#: found, and every trial would give no result. ``SYSTEMROOT`` and the other
#: Windows names stay because Python there needs them for sockets and ``random``.
_SUITE_ENV_NAMES: Final = frozenset(
    {
        "PATH", "HOME", "USER", "LOGNAME", "LANG", "TZ", "TMPDIR", "TEMP", "TMP",
        "PYTHONPATH", "PYTHONHOME", "PYTHONUTF8", "PYTHONIOENCODING", "VIRTUAL_ENV",
        "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "PATHEXT", "WINDIR", "USERPROFILE",
        "APPDATA", "LOCALAPPDATA",
    }
)  # fmt: skip

#: Name prefixes the scoring suite keeps too: the ``LC_*`` locale categories.
_SUITE_ENV_PREFIXES: Final = ("LC_",)

#: The modules the suite's ``python -m pytest --cov`` imports from this interpreter.
_SUITE_TOOLCHAIN: Final = ("pytest", "pytest_cov")


class UnscorableSuiteError(ExitTwoError):
    """The scoring suite cannot judge the agent fairly, so the sample cannot be scored (exit 2)."""


class SuiteToolchainError(UnscorableSuiteError):
    """This interpreter lacks a module the scoring suite runs: the environment's fault."""


class BaselineSuiteError(UnscorableSuiteError):
    """The ``setup/`` baseline's own suite gave no result: the sample author's to fix."""


def require_suite_toolchain(rubric: Rubric) -> None:
    """Raise :class:`SuiteToolchainError` when ``rubric`` runs the suite and a module is missing.

    Why in this process: the suite runs this interpreter in the candidate tree,
    where a ``pytest.py`` can fake any output or exit code, so the run cannot tell
    a missing pytest-cov from the agent's crash. Without it every trial scored 0.
    The runner calls it before any agent runs, :func:`score` before the suite.

    Example::

        >>> require_suite_toolchain(compile_eval_sample(sample).per_trial)  # doctest: +SKIP
    """
    if _execution_metrics(rubric):
        _require_toolchain()


def _require_toolchain() -> None:
    """Raise :class:`SuiteToolchainError` naming each suite module this interpreter lacks."""
    missing = [name for name in _SUITE_TOOLCHAIN if not _importable(name)]
    if missing:
        raise SuiteToolchainError(
            f"the scoring suite runs {sys.executable} -m pytest --cov, which cannot import "
            f"{', '.join(missing)}: install the playbook's dev extra into that interpreter"
        )


def _importable(name: str) -> bool:
    """Whether this interpreter can import ``name``; the seam a test replaces."""
    return importlib.util.find_spec(name) is not None


def _execution_metrics(rubric: Rubric) -> list[Metric]:
    """The metrics ``rubric`` references that run the test suite."""
    return [m for m in referenced_metrics(rubric.checks) if not m.needs_judge and m.needs_project]


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

    ``suite_failure`` is why the candidate's suite gave no result, or ``None``.
    """

    candidate: list[Measurement]
    baseline: list[Measurement]
    project: ProjectHandle | None
    measured_metrics: frozenset[str]
    suite_failure: str | None = None


def _measure(
    rubric: Rubric, sample: EvalSample, candidate: Candidate, stack: ExitStack
) -> _Measured:
    """Measure the candidate and ``sample``'s ``setup/`` with every metric ``rubric`` references.

    Static metrics run per ``*.py`` file; execution metrics run the suite once
    per tree, and only when one is referenced (``run_tests`` is inferred). The
    candidate handle stays open on ``stack``: grading sees it as ``ctx.project``.
    """
    setup = MeasureSetup()
    referenced = referenced_metrics(rubric.checks)
    static = [m for m in referenced if not m.needs_judge and not m.needs_project]
    execution = _execution_metrics(rubric)
    candidate_rows = _static_rows(candidate.tree, static, setup)
    baseline_rows = _static_rows(sample.setup_dir, static, setup)
    promised = measured_metrics(referenced_metrics(rubric.checks, nested=True), setup)
    if not execution:
        return _Measured(candidate_rows, baseline_rows, None, promised)
    _require_toolchain()
    project = _project(candidate.tree, stack)
    candidate_rows += _suite_rows(project, execution, setup)
    baseline_rows += _baseline_suite_rows(sample, execution, setup, stack)
    failure = None if project.no_result is None else project.no_result.reason
    return _Measured(candidate_rows, baseline_rows, project, promised, failure)


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
    """The suite's measurements; none when it gave no result, and ``project.no_result`` says why.

    The candidate's reason reaches grading as ``ctx.suite_failure``, which fails
    every execution check: over no rows they graded zero scopes and passed. A
    command that cannot start raises, as :func:`require_suite_toolchain` does,
    since the environment, not the agent, has to change.
    """
    try:
        return measure_suite(project, metrics, setup)
    except NoSuiteResultError:
        return []


def _baseline_suite_rows(
    sample: EvalSample, metrics: list[Metric], setup: MeasureSetup, stack: ExitStack
) -> list[Measurement]:
    """``sample``'s ``setup/`` suite measurements; :class:`BaselineSuiteError` when it gave none.

    Why raise: ``setup/`` is the sample author's, so its failure is not the agent's
    to carry, and a regression check with no baseline row grades a "new" scope
    against unset bounds and passes. The message names the catalog ``setup/``,
    the tree the author edits, not the temporary copy the suite ran in.
    """
    handle = _project(_setup_copy(sample.setup_dir, stack), stack)
    rows = _suite_rows(handle, metrics, setup)
    if handle.no_result is not None:
        raise BaselineSuiteError(
            f"the setup/ baseline suite of {sample.id} ({sample.setup_dir}) gave no result "
            f"({handle.no_result.reason}); a sample's setup/ suite must finish and write its reports"
        )
    return rows


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


def _project(tree: Path, stack: ExitStack) -> ProjectHandle:
    """A bounded handle over ``tree`` in :func:`_suite_env`; ``stack`` removes its report dir."""
    reports = Path(
        stack.enter_context(tempfile.TemporaryDirectory(prefix="playbook-eval-reports-"))
    )
    return ProjectHandle.create(
        tree,
        reports,
        timeout_s=_SUITE_TIMEOUT_S,
        env_overrides=_suite_env(reports),
        inherit_env=False,
    )


def _suite_env(reports: Path, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """The whole scoring-suite environment: the allowlisted part of ``base``, and its coverage file.

    ``base`` defaults to this process's environment. Only :data:`_SUITE_ENV_NAMES`
    and the :data:`_SUITE_ENV_PREFIXES` names survive, so no secret reaches agent
    code. That also drops every ``PYTEST_*`` name: ``-o addopts=`` does not clear
    ``PYTEST_ADDOPTS``, so a caller's ``-k`` deselected the failing tests, and an
    inherited plugin list or autoload switch broke the run. ``COVERAGE_FILE``
    keeps coverage's data file out of the candidate tree and apart between trials.

    Example::

        >>> sorted(_suite_env(Path("/r"), {"PATH": "/bin", "ANTHROPIC_API_KEY": "k"}))
        ['COVERAGE_FILE', 'PATH']
    """
    source = os.environ if base is None else base
    kept = {name: value for name, value in source.items() if _suite_keeps(name)}
    return {**kept, "COVERAGE_FILE": str(reports / ".coverage")}


def _suite_keeps(name: str) -> bool:
    """Whether the scoring suite keeps the caller's variable ``name``, in any case."""
    upper = name.upper()
    return upper in _SUITE_ENV_NAMES or upper.startswith(_SUITE_ENV_PREFIXES)
